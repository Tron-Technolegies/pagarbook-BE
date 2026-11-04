from django.contrib import admin

from .models import Company, Staff


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "phone", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "email")
    ordering = ("name",)


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = (
        "full_name", "employee_code", "email", "department",
        "designation", "is_active", "company", "created_at",
    )
    list_filter = ("is_active", "department", "company")
    search_fields = ("full_name", "email", "employee_code")
    ordering = ("full_name",)
    raw_id_fields = ("user", "company")
    readonly_fields = ("created_at", "updated_at", "employee_code")
