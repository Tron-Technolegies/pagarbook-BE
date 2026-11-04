from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from attendance.utils import get_attendance_timezone
from authentication.models import Staff
from devices.device_auth import DeviceAuthentication, IsDevice

from .models import Attendance

MAX_BATCH = 500
MAX_FUTURE = timedelta(minutes=5)   # rejects timestamps from a wrong kiosk clock


class DeviceAttendanceItemSerializer(serializers.Serializer):
    client_id = serializers.UUIDField()
    employee_id = serializers.IntegerField()
    attendance_type = serializers.ChoiceField(choices=["check_in", "check_out"])
    timestamp = serializers.DateTimeField()

    def validate_timestamp(self, value):
        if value > timezone.now() + MAX_FUTURE:
            raise serializers.ValidationError("Timestamp is in the future.")
        return value


@api_view(["POST"])
@authentication_classes([DeviceAuthentication])
@permission_classes([IsDevice])
def sync_attendance(request):
    device = request.user.device
    company = request.user.company          # always from the authenticated device

    items = request.data.get("attendance")
    if not isinstance(items, list) or not items:
        return Response({"message": "'attendance' must be a non-empty list"}, status=400)
    if len(items) > MAX_BATCH:
        return Response({"message": f"Send at most {MAX_BATCH} records per request"}, status=400)

    wanted_ids = {i.get("employee_id") for i in items if isinstance(i, dict)}
    wanted_ids = {i for i in wanted_ids if isinstance(i, int)}
    valid_employees = set(
        Staff.objects.filter(company=company, id__in=wanted_ids).values_list("id", flat=True)
    )

    results, created_n, duplicate_n, failed_n = [], 0, 0, 0
    cooldown_seconds = getattr(settings, "ATTENDANCE_COOLDOWN_SECONDS", 300)
    cooldown_delta = timedelta(seconds=cooldown_seconds)

    for raw in items:
        ser = DeviceAttendanceItemSerializer(data=raw if isinstance(raw, dict) else {})
        if not ser.is_valid():
            failed_n += 1
            results.append({
                "client_id": raw.get("client_id") if isinstance(raw, dict) else None,
                "status": "failed",
                "reason": ser.errors,
            })
            continue

        d = ser.validated_data
        cid = str(d["client_id"])

        if d["employee_id"] not in valid_employees:
            failed_n += 1
            results.append({"client_id": cid, "status": "failed", "reason": "employee_not_found"})
            continue

        # 1. Accidental repeated face scan of same type within cooldown window
        # (e.g. employee scanned face twice within 5 minutes for check_in or check_out)
        recent_same_type = Attendance.objects.filter(
            company=company,
            employee_id=d["employee_id"],
            attendance_type=d["attendance_type"],
            timestamp__range=(d["timestamp"] - cooldown_delta, d["timestamp"] + cooldown_delta),
        ).exists()

        if recent_same_type:
            duplicate_n += 1
            results.append({
                "client_id": cid,
                "status": "duplicate",
                "reason": f"repeated_{d['attendance_type']}_within_cooldown",
            })
            continue

        # 2. Check for consecutive duplicate check-ins without an intervening check-out on the same day
        if d["attendance_type"] == "check_in":
            tz = get_attendance_timezone()
            punch_date = timezone.localtime(d["timestamp"], timezone=tz).date()
            last_punch_today = Attendance.objects.filter(
                company=company,
                employee_id=d["employee_id"],
                timestamp__date=punch_date,
            ).order_by("-timestamp").first()

            if last_punch_today and last_punch_today.attendance_type == "check_in":
                duplicate_n += 1
                results.append({
                    "client_id": cid,
                    "status": "duplicate",
                    "reason": "already_checked_in",
                })
                continue

        try:
            with transaction.atomic():
                Attendance.objects.create(
                    company=company,
                    employee_id=d["employee_id"],
                    device=device,
                    attendance_type=d["attendance_type"],
                    source="face",
                    timestamp=d["timestamp"],
                    is_synced=True,
                    client_id=d["client_id"],
                )
            created_n += 1
            results.append({"client_id": cid, "status": "created"})
        except IntegrityError:
            duplicate_n += 1
            results.append({"client_id": cid, "status": "duplicate"})

    device.last_synced_at = timezone.now()
    device.save(update_fields=["last_synced_at"])

    return Response({
        "message": "Sync completed",
        "synced": created_n + duplicate_n,
        "created": created_n,
        "duplicates": duplicate_n,
        "failed": failed_n,
        "results": results,
    })
