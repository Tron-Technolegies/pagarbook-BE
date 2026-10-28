from rest_framework import serializers

from authentication.models import Staff
from devices.models import Device
from .models import Attendance


class AttendanceCreateSerializer(serializers.ModelSerializer):
    employee_id = serializers.PrimaryKeyRelatedField(
        queryset=Staff.objects.all(), source="employee"
    )
    device_id = serializers.PrimaryKeyRelatedField(
        queryset=Device.objects.all(), source="device",
        required=False, allow_null=True,
    )

    class Meta:
        model = Attendance
        fields = [
            "id", "employee_id", "device_id", "attendance_type",
            "source", "timestamp", "is_synced",
        ]

    def validate(self, data):
        user = self.context["request"].user
        staff = getattr(user, "staff", None)
        if staff is None:
            raise serializers.ValidationError({"non_field_errors": ["Staff record not found."]})
        company = staff.company
        employee = data["employee"]
        device = data.get("device")

        if employee.company_id != company.id:
            raise serializers.ValidationError(
                {"employee_id": "Employee does not belong to your company."}
            )
        if device and device.company_id != company.id:
            raise serializers.ValidationError(
                {"device_id": "Device does not belong to your company."}
            )
        return data


class AttendanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    device_name = serializers.CharField(source="device.name", read_only=True, default=None)

    class Meta:
        model = Attendance
        fields = [
            "id", "employee", "employee_name", "device", "device_name",
            "attendance_type", "source", "timestamp", "is_synced", "created_at",
        ]


class AttendanceUpdateSerializer(serializers.ModelSerializer):
    # Only these fields can be corrected
    class Meta:
        model = Attendance
        fields = ["attendance_type", "timestamp"]