from django.contrib.auth.models import User
from django.db import models, transaction


class Company(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    website = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Staff(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="staff_members")
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="staff", null=True, blank=True)

    full_name = models.CharField(max_length=255)
    employee_code = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    department = models.CharField(max_length=100, blank=True)
    designation = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        ordering = ["full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "employee_code"],
                condition=~models.Q(employee_code=""),
                name="unique_employee_code_per_company",
            )
        ]
 
    def save(self, *args, **kwargs):
        with transaction.atomic():
            super().save(*args, **kwargs)
            if not self.employee_code:
                self.employee_code = f"EMP{self.pk:04d}"
                super().save(update_fields=["employee_code"])
 
    def __str__(self):
        return f"{self.full_name} ({self.company.name})"
 