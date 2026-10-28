from django.db import models

from authentication.models import Company, Staff
from devices.models import Device


class Attendance(models.Model):

    ATTENDANCE_TYPE_CHOICES = [
        ("check_in", "Check In"),
        ("check_out", "Check Out"),
    ]

    SOURCE_CHOICES = [
        ("face", "Face Recognition"),
        ("manual", "Manual"),
    ]

    company = models.ForeignKey(Company,on_delete=models.CASCADE,related_name="attendances",)
    employee = models.ForeignKey(Staff,on_delete=models.PROTECT,related_name="attendances",)
    device = models.ForeignKey(Device,on_delete=models.SET_NULL,null=True,blank=True,related_name="attendances",)

    attendance_type = models.CharField(max_length=20,choices=ATTENDANCE_TYPE_CHOICES,)
    source = models.CharField(max_length=20,choices=SOURCE_CHOICES,default="face",)
    timestamp = models.DateTimeField()
    is_synced = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    client_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        constraints = [
            models.UniqueConstraint(
                fields=["device", "client_id"],
                condition=models.Q(client_id__isnull=False),
                name="unique_client_id_per_device",
            )
        ]

    def __str__(self):
        return f"{self.employee.full_name} - {self.attendance_type}"