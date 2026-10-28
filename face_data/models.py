from django.db import models

from authentication.models import Company, Staff


class FaceData(models.Model):
    company = models.ForeignKey(Company,on_delete=models.CASCADE,related_name="face_data",)
    employee = models.OneToOneField(Staff,on_delete=models.CASCADE,related_name="face_data",)
    embedding = models.JSONField(null=True,blank=True,)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["employee__full_name"]

    def __str__(self):
        return f"Face data - {self.employee.full_name}"