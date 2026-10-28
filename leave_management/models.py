from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import models

from authentication.models import Company, Staff


class LeaveType(models.Model):
    company = models.ForeignKey(Company,on_delete=models.CASCADE,related_name="leave_types")

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_paid = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"],
                name="unique_leave_type_per_company"
            )
        ]

    def __str__(self):
        return f"{self.name} - {self.company.name}"


class LeaveRequest(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]

    LEAVE_DURATION_CHOICES = [
        ("full_day", "Full Day"),
        ("first_half", "First Half"),
        ("second_half", "Second Half"),
    ]

    HALF_DAY_DURATIONS = ["first_half", "second_half"]
    ACTIVE_STATUSES = ["pending", "approved"]

    company = models.ForeignKey(Company,on_delete=models.PROTECT,related_name="leave_requests")

    employee = models.ForeignKey(Staff,on_delete=models.PROTECT,related_name="leave_requests")

    leave_type = models.ForeignKey(LeaveType,on_delete=models.PROTECT,related_name="leave_requests")

    start_date = models.DateField()
    end_date = models.DateField()

    duration = models.CharField(max_length=20,choices=LEAVE_DURATION_CHOICES,default="full_day")

    reason = models.TextField()

    status = models.CharField(max_length=20,choices=STATUS_CHOICES,default="pending")

    reviewed_by = models.ForeignKey(Staff,on_delete=models.PROTECT,related_name="reviewed_leave_requests",null=True,blank=True)

    review_comment = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def _has_overlapping_request(self):
        """
        True if the same employee already has a pending/approved request
        overlapping these dates. The only allowed overlap is the opposite
        half of the same single day (first half + second half).
        """
        overlapping = LeaveRequest.objects.filter(
            employee_id=self.employee_id,
            status__in=self.ACTIVE_STATUSES,
            start_date__lte=self.end_date,
            end_date__gte=self.start_date,
        )

        if self.pk:
            overlapping = overlapping.exclude(pk=self.pk)

        if (
            self.duration in self.HALF_DAY_DURATIONS
            and self.start_date == self.end_date
        ):
            opposite = (
                "second_half"
                if self.duration == "first_half"
                else "first_half"
            )
            overlapping = overlapping.exclude(
                start_date=self.start_date,
                end_date=self.start_date,
                duration=opposite,
            )

        return overlapping.exists()

    def clean(self):
        errors = {}
        dates_valid = False

        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                errors["end_date"] = (
                    "End date cannot be earlier than start date."
                )
            else:
                dates_valid = True

            if (
                self.start_date != self.end_date
                and self.duration in self.HALF_DAY_DURATIONS
            ):
                errors["duration"] = (
                    "Half-day leave must be requested for a single day."
                )

        if self.employee_id and self.company_id:
            if self.employee.company_id != self.company_id:
                errors["employee"] = (
                    "Employee must belong to the selected company."
                )

        if self.leave_type_id and self.company_id:
            if self.leave_type.company_id != self.company_id:
                errors["leave_type"] = (
                    "Leave type must belong to the selected company."
                )

        if (
            dates_valid
            and "duration" not in errors
            and self.employee_id
            and self.status in self.ACTIVE_STATUSES
            and self._has_overlapping_request()
        ):
            errors[NON_FIELD_ERRORS] = (
                "An overlapping pending or approved leave request "
                "already exists for these dates."
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return (
            f"{self.employee.full_name} - "
            f"{self.start_date} to {self.end_date}"
        )