from django.utils import timezone
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from authentication.models import Staff
from .device_auth import (
    DeviceAccessToken,
    DeviceAuthentication,
    IsDevice,
    make_device_token,
)
from .models import Device


class DeviceAuthThrottle(AnonRateThrottle):
    scope = "device_auth"


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([DeviceAuthThrottle])
def device_auth(request):
    device_id = request.data.get("device_id")
    device_key = request.data.get("device_key")
    # company_id narrows the lookup to a single tenant when two companies
    # share the same device_id (supported after migration 0003).
    # Clients that omit company_id continue to work as before (first-match
    # fallback) until all kiosk apps are updated.
    company_id = request.data.get("company_id")

    if not device_id or not device_key:
        return Response({"message": "device_id and device_key are required"}, status=400)

    qs = Device.objects.select_related("company").filter(device_id=device_id)
    if company_id is not None:
        try:
            company_id = int(company_id)
        except (TypeError, ValueError):
            return Response({"message": "Invalid company_id"}, status=400)
        qs = qs.filter(company_id=company_id)

    device = qs.first()

    # Same response for "no such device" and "wrong key" so device IDs can't be enumerated
    if device is None or not device.check_key(device_key):
        return Response({"message": "Invalid device credentials"}, status=401)

    if not device.is_active or not device.company.is_active:
        return Response({"message": "Device is inactive"}, status=403)

    device.last_auth_at = timezone.now()
    device.save(update_fields=["last_auth_at"])

    return Response({
        "message": "Device authenticated successfully",
        "access_token": make_device_token(device),
        "expires_in": int(DeviceAccessToken.lifetime.total_seconds()),
        "device": {
            "id": device.id,
            "device_id": device.device_id,
            "company_id": device.company_id,
            "name": device.name,
        },
    })


@api_view(["GET"])
@authentication_classes([DeviceAuthentication])
@permission_classes([IsDevice])
def device_employees(request):
    company = request.user.company  # always taken from the authenticated device
    staff = Staff.objects.filter(company=company, is_active=True)

    data = [
        {
            "id": s.id,
            "employee_code": s.employee_code,
            "full_name": s.full_name,
            "department": s.department,
            "designation": s.designation,
        }
        for s in staff
    ]
    return Response({"count": len(data), "employees": data})