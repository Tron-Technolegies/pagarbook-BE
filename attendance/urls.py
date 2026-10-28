from django.urls import path

from attendance.device_views import sync_attendance
from . import views

urlpatterns = [
    # Normalized routes
    path("add/", views.add_attendance, name="attendance-add"),
    path("view/", views.view_attendance, name="attendance-view"),
    path("single/view/<int:id>/", views.single_view_attendance, name="attendance-single"),
    path("update/<int:id>/", views.update_attendance, name="attendance-update"),
    path("delete/<int:id>/", views.delete_attendance, name="attendance-delete"),

    path("report/summary/", views.attendance_summary, name="attendance-report-summary"),
    path("report/employee/<int:id>/", views.employee_attendance_report, name="attendance-report-employee"),
    path("report/daily/", views.daily_attendance_report, name="attendance-report-daily"),
    path("sync/", sync_attendance, name="attendance-sync"),

    # Backward-compatible legacy routes
    path("attendance/add/", views.add_attendance),
    path("attendance/view/", views.view_attendance),
    path("attendance/single/view/<int:id>/", views.single_view_attendance),
    path("attendance/update/<int:id>/", views.update_attendance),
    path("attendance/delete/<int:id>/", views.delete_attendance),

    path("attendance/report/summary/", views.attendance_summary),
    path("attendance/report/employee/<int:id>/", views.employee_attendance_report),
    path("attendance/report/daily/", views.daily_attendance_report),

    path("device/attendance/sync/", sync_attendance, name="device-attendance-sync"),
]