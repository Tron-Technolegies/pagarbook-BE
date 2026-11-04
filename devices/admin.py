from django.contrib import admin

from .models import Device


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = (
        "name", "device_id", "company", "location",
        "is_active", "last_auth_at", "created_at",
    )
    list_filter = ("is_active", "company")
    search_fields = ("name", "device_id", "company__name")
    ordering = ("name",)
    readonly_fields = (
        "device_key_hash", "key_rotated_at", "last_auth_at",
        "created_at", "updated_at",
    )
