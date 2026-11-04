from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path('staff/signup/', views.user_signup, name='signup'),
    path('staff/login/', views.user_login, name='login'),
    path('staff/logout/', views.user_logout, name='logout'),
    path('staff/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),

    path('staff/add/', views.add_staff, name='staff-add'),
    path('staff/me/', views.staff_me, name='staff-me'),
    path('staff/view/', views.view_staff, name='staff-view'),
    path('staff/single/view/<int:id>/', views.view_single_staff, name='staff-single'),
    path('staff/update/<int:id>/', views.update_staff, name='staff-update'),
    path('staff/delete/<int:id>/', views.delete_staff, name='staff-delete'),
    path('staff/resend-invite/<int:id>/', views.resend_invitation, name='staff-resend-invite'),

    # Public invitation endpoints (no auth required)
    path('invitation/verify/', views.verify_invitation, name='invitation-verify'),
    path('invitation/accept/', views.accept_invitation, name='invitation-accept'),
]