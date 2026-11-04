from django.contrib import admin

from .models import Attendance


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = (
        "employee", "company", "attendance_type", "source",
        "timestamp", "is_synced", "device",
    )
    list_filter = ("attendance_type", "source", "is_synced", "company")
    search_fields = ("employee__full_name", "employee__employee_code")
    ordering = ("-timestamp",)
    date_hierarchy = "timestamp"
    raw_id_fields = ("employee", "company", "device")
    readonly_fields = ("created_at", "client_id")
