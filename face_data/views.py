from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.utils import company_or_error, is_management_user
from .models import FaceData
from .serializers import FaceDataSerializer


api_view(["POST"])
@permission_classes([IsAuthenticated])
def register_face_embedding(request):
    company, err = company_or_error(request)
    if err:
        return err

    if not is_management_user(request.user):
        return Response({"message": "Permission denied. Management access required."}, status=403)
    
    serializer = FaceDataSerializer(
        data=request.data,
        context={"request": request},
    )

    if not serializer.is_valid():
        return Response(
            {
                "message": "Invalid face data.",
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    employee = serializer.validated_data["employee"]

    # Employee can have only one registered face
    face_data, created = FaceData.objects.update_or_create(
        company=company,
        employee=employee,
        defaults={
            "embedding": serializer.validated_data["embedding"],
        },
    )

    return Response(
        {
            "message": (
                "Face embedding registered successfully"
                if created
                else "Face embedding updated successfully"
            ),
            "data": FaceDataSerializer(
                face_data,
                context={"request": request},
            ).data,
        },
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )