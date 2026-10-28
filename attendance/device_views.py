from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

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