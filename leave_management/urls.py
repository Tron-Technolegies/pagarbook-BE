from django.urls import path
from . import views

urlpatterns = [
    path('leave_type/', views.view_leave_types, name='leave-type-list'),
    path('leave_type/create/', views.add_leave_type, name='leave-type-add'),
    path('leave_type/single/view/<int:pk>/', views.view_single_leave_type, name='leave-type-single'),
    path('leave_type/update/<int:pk>/', views.update_leave_type, name='leave-type-update'),
    path('leave_type/delete/<int:pk>/', views.delete_leave_type, name='leave-type-delete'),

    path('apply/', views.apply_for_leave, name='leave-apply'),
    path('leave_requests/', views.view_leave_requests, name='my-leave-requests'),
    path('leave_requests/single/view/<int:pk>/', views.view_single_leave_request, name='leave-request-single'),
    path('leave_requests/cancel/<int:pk>/', views.cancel_leave_request, name='leave-request-cancel'),

    path('manage/leave_requests/', views.manage_leave_requests, name='manage-leave-requests'),
    path('leave_requests/approve/<int:pk>/', views.approve_leave_request, name='leave-request-approve'),
    path('leave_requests/reject/<int:pk>/', views.reject_leave_request, name='leave-request-reject'),
]