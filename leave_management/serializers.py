from rest_framework import serializers

from .models import LeaveType, LeaveRequest


class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = [
            "id",
            "name",
            "description",
            "is_paid",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_name(self, value):
        """
        company is not a serializer field, so DRF cannot enforce the
        (company, name) unique constraint. Check it here (case-insensitive).
        Pass context={"company": company} when saving.
        """
        company = self.context.get("company")

        if company is not None:
            duplicates = LeaveType.objects.filter(
                company=company,
                name__iexact=value,
            )

            if self.instance is not None:
                duplicates = duplicates.exclude(pk=self.instance.pk)

            if duplicates.exists():
                raise serializers.ValidationError(
                    "A leave type with this name already exists."
                )

        return value


class LeaveRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(
        source="employee.full_name",
        read_only=True
    )

    employee_code = serializers.CharField(
        source="employee.employee_code",
        read_only=True
    )

    leave_type_name = serializers.CharField(
        source="leave_type.name",
        read_only=True
    )

    reviewed_by_name = serializers.CharField(
        source="reviewed_by.full_name",
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = LeaveRequest
        fields = [
            "id",
            "employee",
            "employee_name",
            "employee_code",
            "leave_type",
            "leave_type_name",
            "start_date",
            "end_date",
            "duration",
            "reason",
            "status",
            "reviewed_by",
            "reviewed_by_name",
            "review_comment",
            "reviewed_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "employee",
            "status",
            "reviewed_by",
            "reviewed_by_name",
            "review_comment",
            "reviewed_at",
            "created_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # When a company is passed in the context, only that company's
        # active leave types are accepted. Other companies' IDs and
        # nonexistent IDs then produce the same error.
        company = self.context.get("company")

        if company is not None:
            self.fields["leave_type"].queryset = LeaveType.objects.filter(
                company=company,
                is_active=True,
            )

    def validate(self, attrs):
        start_date = attrs.get("start_date")
        end_date = attrs.get("end_date")
        duration = attrs.get("duration", "full_day")

        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError({
                "end_date": "End date cannot be earlier than start date."
            })

        if (
            start_date
            and end_date
            and start_date != end_date
            and duration in ["first_half", "second_half"]
        ):
            raise serializers.ValidationError({
                "duration": "Half-day leave must be for a single day."
            })

        return attrs


class LeaveReviewSerializer(serializers.Serializer):
    review_comment = serializers.CharField(
        required=False,
        allow_blank=True,
    )