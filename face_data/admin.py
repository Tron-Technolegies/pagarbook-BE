from django.contrib import admin

from .models import FaceData


@admin.register(FaceData)
class FaceDataAdmin(admin.ModelAdmin):
    list_display = ("employee", "company", "created_at", "updated_at")
    list_filter = ("company",)
    search_fields = ("employee__full_name", "employee__employee_code")
    ordering = ("employee__full_name",)
    raw_id_fields = ("employee", "company")
    readonly_fields = ("created_at", "updated_at")
