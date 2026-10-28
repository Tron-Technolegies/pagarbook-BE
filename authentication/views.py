from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from django.contrib.auth.models import User

from .models import Company, Staff
from .serializers import StaffSerializer
from .utils import company_or_error, is_management_user, validation_error


# ─────────────────────── authentication CRUD ───────────────────────────

def build_auth_response(user, message=None, status=200):
    refresh = RefreshToken.for_user(user)
    staff = getattr(user, "staff", None)
    company = staff.company if staff else None
    data = {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": {
            "id": user.id,
            "name": user.first_name,
            "email": user.email,
            "companyId": company.id if company else None,
            "companyName": company.name if company else "",
        },
    }
    if message:
        data["message"] = message
    return Response(data, status=status)


@api_view(["POST"])
@permission_classes([AllowAny])
@transaction.atomic
def user_signup(request):
    name = request.data.get("name", "").strip()
    email = request.data.get("email", "").strip().lower()
    password = request.data.get("password", "")

    company_name = request.data.get("company_name", "").strip()
    company_email = request.data.get("company_email", "").strip().lower()
    company_phone = request.data.get("company_phone", "").strip()
    company_website = request.data.get("company_website", "").strip()

    if not name:
        return Response({"message": "Name is required"}, status=400)
    if not email:
        return Response({"message": "Email is required"}, status=400)
    if not password:
        return Response({"message": "Password is required"}, status=400)
    if not company_name:
        return Response({"message": "Company name is required"}, status=400)
    if not company_email:
        return Response({"message": "Company email is required"}, status=400)

    try:
        validate_password(password)  # uses AUTH_PASSWORD_VALIDATORS (min length 8 etc.)
    except ValidationError as e:
        return Response({"message": " ".join(e.messages)}, status=400)

    if User.objects.filter(email__iexact=email).exists():
        return Response({"message": "User email already exists"}, status=400)
    if Company.objects.filter(email__iexact=company_email).exists():
        return Response({"message": "Company email already exists"}, status=400)

    company = Company.objects.create(
        name=company_name,
        email=company_email,
        phone=company_phone,
        website=company_website,
    )
    user = User.objects.create_user(
        username=email,
        email=email,
        password=password,
        first_name=name,
    )
    Staff.objects.create(
        company=company,
        user=user,
        full_name=name,
        email=email,
        department="Management",
    )
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])

    return build_auth_response(user, "Company created successfully", status=201)


@api_view(["POST"])
@permission_classes([AllowAny])
def user_login(request):
    email = request.data.get("email", "").strip().lower()
    password = request.data.get("password", "")

    if not email:
        return Response({"message": "Email is required"}, status=400)
    if not password:
        return Response({"message": "Password is required"}, status=400)

    user_obj = User.objects.select_related("staff__company").filter(email__iexact=email).first()

    # Same error for "no such user" and "wrong password" so emails can't be probed.
    if user_obj is None:
        return Response({"message": "Invalid email or password"}, status=401)

    user = authenticate(request, username=user_obj.username, password=password)

    if user is None:
        if user_obj.check_password(password) and not user_obj.is_active:
            return Response({"message": "Your account has been deactivated."}, status=403)
        return Response({"message": "Invalid email or password"}, status=401)

    staff = getattr(user, "staff", None)
    if staff is None:
        return Response({"message": "Staff record not found"}, status=404)
    if not staff.company.is_active:
        return Response({"message": "Your company has been deactivated."}, status=403)

    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])

    return build_auth_response(user)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def user_logout(request):
    refresh_token = request.data.get("refresh")
    if not refresh_token:
        return Response({"message": "Refresh token is required"}, status=400)
    try:
        RefreshToken(refresh_token).blacklist()
    except TokenError:
        return Response({"message": "Invalid or expired token"}, status=400)
    return Response({"message": "Logged out successfully"})




# ─────────────────────── staff CRUD ───────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_staff(request):
    company, err = company_or_error(request)
    if err:
        return err

    serializer = StaffSerializer(data=request.data, context={"company": company})
    if not serializer.is_valid():
        return validation_error(serializer)

    staff = serializer.save(company=company)
    return Response(
        {"message": "Staff added successfully", "data": StaffSerializer(staff).data},
        status=201,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def view_staff(request):
    company, err = company_or_error(request)
    if err:
        return err

    qs = Staff.objects.filter(company=company)

    search = request.query_params.get("search", "").strip()
    if search:
        qs = qs.filter(
            Q(full_name__icontains=search)
            | Q(employee_code__icontains=search)
            | Q(department__icontains=search)
        )

    is_active = request.query_params.get("is_active")
    if is_active in ("true", "false"):
        qs = qs.filter(is_active=(is_active == "true"))

    return Response(StaffSerializer(qs, many=True).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def view_single_staff(request, id):
    company, err = company_or_error(request)
    if err:
        return err

    staff = Staff.objects.filter(company=company, id=id).first()
    if staff is None:
        return Response({"message": "Staff not found"}, status=404)
    return Response(StaffSerializer(staff).data)


@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def update_staff(request, id):
    company, err = company_or_error(request)
    if err:
        return err

    staff = Staff.objects.filter(company=company, id=id).first()
    if staff is None:
        return Response({"message": "Staff not found"}, status=404)

    serializer = StaffSerializer(
        staff, data=request.data, partial=True, context={"company": company}
    )
    if not serializer.is_valid():
        return validation_error(serializer)

    staff = serializer.save()
    return Response({"message": "Staff updated successfully", "data": StaffSerializer(staff).data})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_staff(request, id):
    company, err = company_or_error(request)
    if err:
        return err

    if not is_management_user(request.user):
        return Response({"message": "Permission denied. Management access required."}, status=403)

    staff = Staff.objects.filter(company=company, id=id).first()
    if staff is None:
        return Response({"message": "Staff not found"}, status=404)
    if staff.user_id is not None:
        return Response({"message": "This staff has a login account and cannot be deleted"}, status=400)
    if staff.attendances.exists():
        return Response(
            {"message": "Cannot delete staff with existing attendance records. Deactivate the staff member instead."},
            status=400,
        )

    staff.delete()
    return Response({"message": "Staff deleted successfully"})