from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from authentication.utils import company_or_error, is_management_user, validation_error

from .models import Device
from .serializers import DeviceSerializer


# ─────────────────────────── device CRUD ───────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_device(request):
    company, err = company_or_error(request)
    if err:
        return err

    if not is_management_user(request.user):
        return Response({"message": "Permission denied. Management access required."}, status=403)

    serializer = DeviceSerializer(data=request.data)
    if not serializer.is_valid():
        return validation_error(serializer)

    device = serializer.save(company=company)
    raw_key = device.issue_new_key()   # NEW

    return Response(
        {
            "message": "Device registered successfully",
            "data": DeviceSerializer(device).data,
            "device_key": raw_key,     # NEW: shown only this once
        },
        status=201,
    )

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def view_devices(request):
    company, err = company_or_error(request)
    if err:
        return err

    qs = Device.objects.filter(company=company)

    search = request.query_params.get("search", "").strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search) | Q(device_id__icontains=search) | Q(location__icontains=search)
        )

    is_active = request.query_params.get("is_active")
    if is_active in ("true", "false"):
        qs = qs.filter(is_active=(is_active == "true"))

    return Response(DeviceSerializer(qs, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def view_single_device(request, id):
    company, err = company_or_error(request)
    if err:
        return err

    device = Device.objects.filter(company=company, id=id).first()
    if device is None:
        return Response({"message": "Device not found"}, status=404)
    return Response(DeviceSerializer(device).data)


@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def update_device(request, id):
    company, err = company_or_error(request)
    if err:
        return err

    if not is_management_user(request.user):
        return Response({"message": "Permission denied. Management access required."}, status=403)

    device = Device.objects.filter(company=company, id=id).first()
    if device is None:
        return Response({"message": "Device not found"}, status=404)

    serializer = DeviceSerializer(device, data=request.data, partial=True)
    if not serializer.is_valid():
        return validation_error(serializer)

    device = serializer.save()
    return Response({"message": "Device updated successfully", "data": DeviceSerializer(device).data})



@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_device(request, id):
    company, err = company_or_error(request)
    if err:
        return err

    if not is_management_user(request.user):
        return Response({"message": "Permission denied. Management access required."}, status=403)

    device = Device.objects.filter(company=company, id=id).first()
    if device is None:
        return Response({"message": "Device not found"}, status=404)

    device.delete()
    return Response({"message": "Device deleted successfully"})



@api_view(["POST"])
@permission_classes([IsAuthenticated])
def regenerate_device_key(request, id):
    company, err = company_or_error(request)
    if err:
        return err

    if not is_management_user(request.user):
        return Response({"message": "Permission denied. Management access required."}, status=403)

    device = Device.objects.filter(company=company, id=id).first()
    if device is None:
        return Response({"message": "Device not found"}, status=404)

    raw_key = device.issue_new_key()
    return Response({
        "message": "New device key generated. It will not be shown again.",
        "device_id": device.device_id,
        "device_key": raw_key,
    })