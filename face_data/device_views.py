import math

from django.conf import settings
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from authentication.models import Staff
from devices.device_auth import DeviceAuthentication, IsDevice

from .models import FaceData


class DeviceFaceEmbeddingSerializer(serializers.Serializer):
    employee_id = serializers.IntegerField()
    embedding = serializers.ListField(
        child=serializers.FloatField(), allow_empty=False, max_length=2048
    )

    def validate_embedding(self, value):
        if not all(math.isfinite(x) for x in value):
            raise serializers.ValidationError("Embedding contains invalid numbers.")
        # optional: set FACE_EMBEDDING_DIM in settings to your model's embedding size
        dim = getattr(settings, "FACE_EMBEDDING_DIM", None)
        if dim and len(value) != dim:
            raise serializers.ValidationError(f"Embedding must have {dim} values.")
        return value


@api_view(["POST"])
@authentication_classes([DeviceAuthentication])
@permission_classes([IsDevice])
def device_register_face(request):
    company = request.user.company          # always from the authenticated device

    ser = DeviceFaceEmbeddingSerializer(data=request.data)
    if not ser.is_valid():
        return Response({"message": "Invalid face data.", "errors": ser.errors}, status=400)

    # looked up inside the device's own company only
    employee = Staff.objects.filter(
        id=ser.validated_data["employee_id"], company=company
    ).first()
    if employee is None:
        return Response({"message": "Employee not found"}, status=404)

    face, created = FaceData.objects.update_or_create(
        company=company,
        employee=employee,
        defaults={"embedding": ser.validated_data["embedding"]},
    )

    return Response(
        {
            "message": "Face embedding registered successfully" if created
                       else "Face embedding updated successfully",
            "data": {"id": face.id, "employee_id": employee.id},
        },
        status=201 if created else 200,
    )

@api_view(["GET"])
@authentication_classes([DeviceAuthentication])
@permission_classes([IsDevice])
def device_face_data(request):
    company = request.user.company          # always from the authenticated device

    qs = FaceData.objects.filter(
        company=company,
        employee__is_active=True,
        embedding__isnull=False,
    ).order_by("updated_at")

    since = request.query_params.get("updated_since")
    if since:
        dt = parse_datetime(since)
        if dt is None or timezone.is_naive(dt):
            return Response(
                {"message": "updated_since must be an ISO datetime with timezone, e.g. 2026-10-06T00:00:00Z"},
                status=400,
            )
        qs = qs.filter(updated_at__gt=dt)

    server_time = timezone.now()   # taken before the query result is used
    data = [
        {
            "employee_id": f.employee_id,
            "embedding": f.embedding,
            "updated_at": f.updated_at.isoformat(),
        }
        for f in qs
    ]
    return Response({
        "count": len(data),
        "server_time": server_time.isoformat(),
        "face_data": data,
    })