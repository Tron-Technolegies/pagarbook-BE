from rest_framework import serializers

from .models import Device


class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = [
            "id", "name", "device_id", "location", "is_active",
            "last_synced_at", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "last_synced_at", "created_at", "updated_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Device name is required")
        return value

    def validate_device_id(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Device ID is required")

        # self.instance is set only on update: the ID is fixed after registration
        if self.instance:
            if value != self.instance.device_id:
                raise serializers.ValidationError("Device ID cannot be changed after registration")
            return value

        company = self.context.get("company")
        qs = Device.objects.filter(device_id__iexact=value)
        if company:
            qs = qs.filter(company=company)
        if qs.exists():
            raise serializers.ValidationError("Device ID already registered for this company")
        return value
