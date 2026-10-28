from django.urls import path

from face_data.device_views import device_face_data, device_register_face
from . import views

urlpatterns = [
    # Normalized routes
    path("embedding/register/", views.register_face_embedding, name="face-embedding-register"),
    path("device/face-embedding/", device_register_face, name="device-face-register"),
    path("device/face-data/", device_face_data, name="device-face-data"),

    # Backward-compatible legacy routes
    path("face/embedding/register/", views.register_face_embedding),
]