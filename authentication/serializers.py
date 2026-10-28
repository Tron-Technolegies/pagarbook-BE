from rest_framework import serializers

from .models import Staff


class StaffSerializer(serializers.ModelSerializer):
    class Meta:
        model = Staff
        fields = [
            "id", "full_name", "employee_code", "email", "phone",
            "department", "designation", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_full_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Full name is required")
        return value

    def validate_employee_code(self, value):
        value = value.strip()
        if not value:
            return value  # blank -> auto-generated on save
        qs = Staff.objects.filter(company=self.context["company"], employee_code__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Employee code already exists")
        return value