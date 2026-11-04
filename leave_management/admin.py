from django.contrib import admin

from .models import LeaveRequest, LeaveType


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "is_paid", "is_active", "created_at")
    list_filter = ("is_paid", "is_active", "company")
    search_fields = ("name", "company__name")
    ordering = ("name",)


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = (
        "employee", "leave_type", "start_date", "end_date",
        "status", "duration", "company",
    )
    list_filter = ("status", "company")
    search_fields = ("employee__full_name", "employee__employee_code")
    ordering = ("-start_date",)
    date_hierarchy = "start_date"
    raw_id_fields = ("employee", "company", "leave_type", "reviewed_by")
    readonly_fields = ("created_at", "updated_at")
