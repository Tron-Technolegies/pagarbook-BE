from collections import defaultdict
from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from attendance.utils import EMPTY, active_staff, build_day_map, company_records, day_row, day_status, parse_day, parse_range
from authentication.models import Staff
from authentication.utils import company_or_error, is_management_user

from .models import Attendance
from .serializers import (
    AttendanceCreateSerializer,
    AttendanceSerializer,
    AttendanceUpdateSerializer,
)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_attendance(request):
    company, err = company_or_error(request)
    if err:
        return err

    serializer = AttendanceCreateSerializer(
        data=request.data, context={"request": request}
    )
    serializer.is_valid(raise_exception=True)
    attendance = serializer.save(company=company)
    return Response(AttendanceSerializer(attendance).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def view_attendance(request):
    company, err = company_or_error(request)
    if err:
        return err

    qs = (
        Attendance.objects.filter(company=company)
        .select_related("employee", "device")
    )

    params = request.query_params
    if params.get("employee_id"):
        qs = qs.filter(employee_id=params["employee_id"])
    if params.get("device_id"):
        qs = qs.filter(device_id=params["device_id"])
    if params.get("attendance_type"):
        qs = qs.filter(attendance_type=params["attendance_type"])
    if params.get("date"):
        qs = qs.filter(timestamp__date=params["date"])
    if params.get("from") and params.get("to"):
        qs = qs.filter(timestamp__date__range=(params["from"], params["to"]))

    return Response(AttendanceSerializer(qs, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def single_view_attendance(request, id):
    company, err = company_or_error(request)
    if err:
        return err

    attendance = get_object_or_404(Attendance, id=id, company=company)
    return Response(AttendanceSerializer(attendance).data)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_attendance(request, id):
    company, err = company_or_error(request)
    if err:
        return err

    attendance = get_object_or_404(Attendance, id=id, company=company)
    serializer = AttendanceUpdateSerializer(attendance, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save(source="manual")  # mark as manually corrected
    return Response(AttendanceSerializer(attendance).data)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_attendance(request, id):
    company, err = company_or_error(request)
    if err:
        return err

    if not is_management_user(request.user):
        return Response({"message": "Permission denied. Management access required."}, status=403)

    attendance = get_object_or_404(Attendance, id=id, company=company)
    attendance.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


def _bad(msg):
    return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)


# 1. Attendance Summary
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def attendance_summary(request):
    company, err = company_or_error(request)
    if err:
        return err

    department = request.query_params.get("department")
    try:
        start, end = parse_range(request.query_params)
    except ValueError as e:
        return _bad(str(e))

    days = (end - start).days + 1
    staff = list(active_staff(company, department).values("id", "department"))
    dept_of = {s["id"]: s["department"] or "Unassigned" for s in staff}

    records = company_records(company, start, end, department, active_only=True)
    day_map = build_day_map(records)

    totals = {"present": 0, "late": 0}
    by_dept = defaultdict(lambda: {"present": 0, "late": 0, "absent": 0})

    for (emp_id, day), v in day_map.items():
        s = day_status(v["first_in"], day)
        if s == "absent":          # check-out only, no check-in
            continue
        totals["on_time" if s == "present" else "late"] = totals.get(
            "on_time" if s == "present" else "late", 0) + 1
        by_dept[dept_of.get(emp_id, "Unassigned")][s] += 1

    on_time, late = totals.get("on_time", 0), totals["late"]
    present = on_time + late
    expected = len(staff) * days

    dept_staff_count = defaultdict(int)
    for d in dept_of.values():
        dept_staff_count[d] += 1
    departments = []
    for name, count in dept_staff_count.items():
        c = by_dept[name]
        attended = c["present"] + c["late"]
        departments.append({
            "department": name,
            "employees": count,
            "present": attended,
            "late": c["late"],
            "absent": max(count * days - attended, 0),
        })

    return Response({
        "from": start, "to": end, "days": days,
        "total_employees": len(staff),
        "present": present,            # includes late
        "on_time": on_time,
        "late": late,
        "absent": max(expected - present, 0),
        "total_check_ins": records.filter(attendance_type="check_in").count(),
        "total_check_outs": records.filter(attendance_type="check_out").count(),
        "by_department": sorted(departments, key=lambda d: d["department"]),
    })


# 2. Employee Attendance Report
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def employee_attendance_report(request, id):
    company, err = company_or_error(request)
    if err:
        return err

    employee = get_object_or_404(Staff, id=id, company=company)  # inactive staff allowed
    try:
        start, end = parse_range(request.query_params, default_days=30)
    except ValueError as e:
        return _bad(str(e))

    day_map = build_day_map(company_records(company, start, end).filter(employee=employee))

    rows, counts = [], {"present": 0, "late": 0, "absent": 0}
    day = start
    while day <= end:
        row = day_row(day_map.get((employee.id, day), EMPTY), day)
        counts[row["status"]] += 1
        rows.append({"date": day, **row})
        day += timedelta(days=1)

    worked = [r["hours_worked"] for r in rows if r["hours_worked"]]
    return Response({
        "employee": {
            "id": employee.id,
            "employee_code": employee.employee_code,
            "name": employee.full_name,
            "department": employee.department,
            "designation": employee.designation,
            "is_active": employee.is_active,
        },
        "from": start, "to": end,
        "totals": counts,
        "total_hours": round(sum(worked), 2),
        "records": rows,
    })


# 3. Daily Attendance Report
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def daily_attendance_report(request):
    company, err = company_or_error(request)
    if err:
        return err

    params = request.query_params
    department = params.get("department")
    status_filter = params.get("status")          # present | late | absent
    try:
        day = parse_day(params.get("date"))
        if day > timezone.localdate():
            return _bad("The selected date is in the future.")
    except ValueError as e:
        return _bad(str(e))

    day_map = build_day_map(company_records(company, day, day, department, active_only=True))

    rows, counts = [], {"present": 0, "late": 0, "absent": 0}
    for emp in active_staff(company, department).order_by("full_name"):
        row = day_row(day_map.get((emp.id, day), EMPTY), day)
        counts[row["status"]] += 1
        if status_filter and row["status"] != status_filter:
            continue
        rows.append({
            "employee_id": emp.id,
            "employee_code": emp.employee_code,
            "employee_name": emp.full_name,
            "department": emp.department,
            "designation": emp.designation,
            **row,
        })

    return Response({"date": day, "totals": counts, "records": rows})