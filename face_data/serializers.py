from rest_framework import serializers

from authentication.models import Staff
from .models import FaceData


class FaceDataSerializer(serializers.ModelSerializer):
    employee_id = serializers.PrimaryKeyRelatedField(
        queryset=Staff.objects.all(),
        source="employee",
    )

    class Meta:
        model = FaceData
        fields = [
            "id",
            "employee_id",
            "embedding",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]

    def validate(self, data):
        user = self.context["request"].user
        staff = getattr(user, "staff", None)
        if staff is None:
            raise serializers.ValidationError({"non_field_errors": ["Staff record not found."]})
        company = staff.company
        employee = data["employee"]

        if employee.company_id != company.id:
            raise serializers.ValidationError({
                "employee_id": "Employee does not belong to your company."
            })

        return data