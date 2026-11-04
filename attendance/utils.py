from datetime import datetime, time, timedelta
import zoneinfo

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_date

from attendance.models import Attendance
from authentication.models import Staff


def get_attendance_timezone():
    tz_name = getattr(settings, "ATTENDANCE_TIME_ZONE", getattr(settings, "TIME_ZONE", "Asia/Kolkata"))
    try:
        return zoneinfo.ZoneInfo(tz_name)
    except Exception:
        return timezone.get_current_timezone()


def parse_day(value):
    if not value:
        tz = get_attendance_timezone()
        return timezone.localtime(timezone.now(), timezone=tz).date()
    d = parse_date(value)
    if not d:
        raise ValueError("Invalid date. Use YYYY-MM-DD.")
    return d


def parse_range(params, default_days=1):
    """(start, end) from ?date= or ?from=&to=; defaults to the last N days. End is capped at today."""
    tz = get_attendance_timezone()
    today = timezone.localtime(timezone.now(), timezone=tz).date()

    if params.get("date"):
        start = end = parse_day(params["date"])
    elif params.get("from") or params.get("to"):
        start, end = parse_date(params.get("from", "")), parse_date(params.get("to", ""))
        if not start or not end:
            raise ValueError("Both 'from' and 'to' are required (YYYY-MM-DD).")
        if start > end:
            raise ValueError("'from' must not be after 'to'.")
    else:
        start, end = today - timedelta(days=default_days - 1), today

    end = min(end, today)
    if start > end:
        raise ValueError("The selected period is in the future.")
    return start, end


def late_threshold(day):
    work_start = getattr(settings, "WORK_START_TIME", time(9, 0))
    grace_minutes = getattr(settings, "LATE_GRACE_MINUTES", 15)
    naive = datetime.combine(day, work_start) + timedelta(minutes=grace_minutes)
    tz = get_attendance_timezone()
    return timezone.make_aware(naive, timezone=tz)


def active_staff(company, department=None):
    qs = Staff.objects.filter(company=company, is_active=True)
    if department:
        qs = qs.filter(department__iexact=department)
    return qs


def company_records(company, start, end, department=None, active_only=False):
    qs = Attendance.objects.filter(
        company=company, timestamp__date__range=(start, end)
    ).select_related("device")
    if active_only:
        qs = qs.filter(employee__is_active=True)
    if department:
        qs = qs.filter(employee__department__iexact=department)
    return qs


def device_info(device):
    if not device:
        return None
    return {"name": device.name, "device_id": device.device_id, "location": device.location}


def build_day_map(records):
    """{(employee_id, local_date): first/last check-in/out with their devices}"""
    result = {}
    tz = get_attendance_timezone()
    for r in records.order_by("timestamp"):
        key = (r.employee_id, timezone.localtime(r.timestamp, timezone=tz).date())
        e = result.setdefault(
            key, {"first_in": None, "last_out": None, "in_device": None, "out_device": None}
        )
        if r.attendance_type == "check_in" and e["first_in"] is None:
            e["first_in"], e["in_device"] = r.timestamp, r.device
        elif r.attendance_type == "check_out":
            e["last_out"], e["out_device"] = r.timestamp, r.device
    return result


EMPTY = {"first_in": None, "last_out": None, "in_device": None, "out_device": None}


def get_approved_leaves_map(company, start, end):
    """Returns {(employee_id, date): duration} for approved leave requests."""
    try:
        from leave_management.models import LeaveRequest
        leaves = LeaveRequest.objects.filter(
            company=company,
            status="approved",
            start_date__lte=end,
            end_date__gte=start,
        ).values("employee_id", "start_date", "end_date", "duration")

        leave_map = {}
        for l in leaves:
            curr = max(l["start_date"], start)
            last = min(l["end_date"], end)
            while curr <= last:
                leave_map[(l["employee_id"], curr)] = l["duration"]
                curr += timedelta(days=1)
        return leave_map
    except Exception:
        return {}


def day_status(first_in, day, leave_info=None):
    if first_in is not None:
        return "late" if first_in > late_threshold(day) else "present"
    if leave_info:
        if leave_info in ("first_half", "second_half"):
            return "half_day_leave"
        return "on_leave"
    return "absent"


def hours_worked(first_in, last_out):
    if first_in and last_out and last_out > first_in:
        return round((last_out - first_in).total_seconds() / 3600, 2)
    return None


def iso(dt):
    tz = get_attendance_timezone()
    return timezone.localtime(dt, timezone=tz).isoformat() if dt else None


def day_row(v, day, leave_info=None):
    """Shared per-day fields used by the employee and daily reports."""
    return {
        "status": day_status(v["first_in"], day, leave_info=leave_info),
        "first_check_in": iso(v["first_in"]),
        "check_in_device": device_info(v["in_device"]),
        "last_check_out": iso(v["last_out"]),
        "check_out_device": device_info(v["out_device"]),
        "hours_worked": hours_worked(v["first_in"], v["last_out"]),
    }
