from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path('staff/signup/', views.user_signup, name='signup'),
    path('staff/login/', views.user_login, name='login'),
    path('staff/logout/', views.user_logout, name='logout'),
    path('staff/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),

    path('staff/add/', views.add_staff, name='staff-add'),
    path('staff/view/', views.view_staff, name='staff-view'),
    path('staff/single/view/<int:id>/', views.view_single_staff, name='staff-single'),
    path('staff/update/<int:id>/', views.update_staff, name='staff-update'),
    path('staff/delete/<int:id>/', views.delete_staff, name='staff-delete'),
]