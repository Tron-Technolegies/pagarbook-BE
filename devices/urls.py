from django.urls import path

from devices import device_views
from . import views

urlpatterns = [
    # Normalized routes
    path('add/', views.add_device, name='device-add'),
    path('view/', views.view_devices, name='device-view'),
    path('single/view/<int:id>/', views.view_single_device, name='device-single'),
    path('update/<int:id>/', views.update_device, name='device-update'),
    path('delete/<int:id>/', views.delete_device, name='device-delete'),
    path('auth/', device_views.device_auth, name='device-auth'),
    path('employees/', device_views.device_employees, name='device-employees'),
    path('regenerate-key/<int:id>/', views.regenerate_device_key, name='device-regenerate-key'),

    # Backward-compatible legacy routes
    path('device/add/', views.add_device),
    path('device/view/', views.view_devices),
    path('device/single/view/<int:id>/', views.view_single_device),
    path('device/update/<int:id>/', views.update_device),
    path('device/delete/<int:id>/', views.delete_device),
    path('device/auth/', device_views.device_auth),
    path('device/employees/', device_views.device_employees),
    path('device/regenerate-key/<int:id>/', views.regenerate_device_key),
]