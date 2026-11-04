from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from django.contrib.auth.models import User

from django.conf import settings
from django.contrib.auth.password_validation import validate_password as _validate_password
from django.core import signing
from django.core.mail import send_mail

from .models import Company, Staff
from .serializers import StaffSerializer
from .utils import company_or_error, is_management_user, validation_error

# ─── invitation helpers ────────────────────────────────────────────────

_INVITE_SALT = "employee-invitation"
_INVITE_MAX_AGE = 7 * 24 * 3600  # 7 days in seconds


def _make_invite_token(staff_id: int) -> str:
    signer = signing.TimestampSigner(salt=_INVITE_SALT)
    return signer.sign(str(staff_id))


def _verify_invite_token(token: str):
    """Return (staff_id: int, error_str|None)."""
    signer = signing.TimestampSigner(salt=_INVITE_SALT)
    try:
        value = signer.unsign(token, max_age=_INVITE_MAX_AGE)
        return int(value), None
    except signing.SignatureExpired:
        return None, "Invitation link has expired. Please request a new one."
    except signing.BadSignature:
        return None, "Invalid invitation link."


def _send_invite_email(staff, token: str):
    portal_url = getattr(settings, "EMPLOYEE_PORTAL_URL", "http://localhost:5173")
    invite_url = "{}/invitation/accept/?token={}".format(portal_url, token)
    subject = "You have been invited to join {} on PagarLens".format(staff.company.name)
    lines = [
        "Hello {},".format(staff.full_name),
        "",
        "You have been added as an employee at {}.".format(staff.company.name),
        "",
        "Click the link below to set your password and activate your account:",
        invite_url,
        "",
        "This link will expire in 7 days.",
        "",
        "If you did not expect this email, please ignore it.",
        "",
        "- PagarLens Team",
    ]
    body = "\n".join(lines)
    from_email = settings.DEFAULT_FROM_EMAIL or "noreply@pagarlens.com"
    send_mail(subject, body, from_email, [staff.email], fail_silently=False)


# ─────────────────────── authentication CRUD ───────────────────────────

class LoginRateThrottle(AnonRateThrottle):
    scope = "login"


def build_auth_response(user, message=None, status=200):
    refresh = RefreshToken.for_user(user)
    staff = getattr(user, "staff", None)
    company = staff.company if staff else None
    management = is_management_user(user)
    data = {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": {
            "id": user.id,
            "name": user.first_name,
            "email": user.email,
            "companyId": company.id if company else None,
            "companyName": company.name if company else "",
            "staffId": staff.id if staff else None,
            "role": "admin" if management else "employee",
            "isManagement": management,
            "department": staff.department if staff else "",
            "designation": staff.designation if staff else "",
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
@throttle_classes([LoginRateThrottle])
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
        staff_obj = getattr(user_obj, "staff", None)
        is_deactivated = (not user_obj.is_active) or (staff_obj is not None and not staff_obj.is_active)
        if user_obj.check_password(password) and is_deactivated:
            return Response({"message": "Your account has been deactivated."}, status=403)
        return Response({"message": "Invalid email or password"}, status=401)

    staff = getattr(user, "staff", None)
    if staff is None:
        return Response({"message": "Staff record not found"}, status=404)
    if not staff.is_active:
        return Response({"message": "Your account has been deactivated."}, status=403)
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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_me(request):
    """Return the authenticated user's own staff profile."""
    company, err = company_or_error(request)
    if err:
        return err

    staff = getattr(request.user, "staff", None)
    if staff is None:
        return Response({"message": "Staff profile not found"}, status=404)

    return Response(StaffSerializer(staff).data)


# ─────────────────────── staff CRUD ───────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_staff(request):
    company, err = company_or_error(request)
    if err:
        return err

    if not is_management_user(request.user):
        return Response({"message": "Permission denied. Management access required."}, status=403)

    serializer = StaffSerializer(data=request.data, context={"company": company})
    if not serializer.is_valid():
        return validation_error(serializer)

    staff = serializer.save(company=company)

    # Send invitation email if staff has an email address and no login yet
    invite_sent = False
    if staff.email and staff.user is None:
        try:
            token = _make_invite_token(staff.id)
            _send_invite_email(staff, token)
            invite_sent = True
        except Exception:
            # Email failure must not roll back staff creation
            pass

    return Response(
        {
            "message": "Staff added successfully",
            "data": StaffSerializer(staff).data,
            "invite_sent": invite_sent,
        },
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

    if not is_management_user(request.user):
        caller_staff = getattr(request.user, "staff", None)
        if caller_staff is None or staff.id != caller_staff.id:
            return Response(
                {"message": "Permission denied. You can only view your own profile."},
                status=403,
            )

    return Response(StaffSerializer(staff).data)


@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def update_staff(request, id):
    company, err = company_or_error(request)
    if err:
        return err

    if not is_management_user(request.user):
        return Response({"message": "Permission denied. Management access required."}, status=403)

    staff = Staff.objects.select_related("user").filter(company=company, id=id).first()
    if staff is None:
        return Response({"message": "Staff not found"}, status=404)

    serializer = StaffSerializer(
        staff, data=request.data, partial=True, context={"company": company}
    )
    if not serializer.is_valid():
        return validation_error(serializer)

    with transaction.atomic():
        staff = serializer.save()
        if "is_active" in serializer.validated_data and staff.user is not None:
            if staff.user.is_active != staff.is_active:
                staff.user.is_active = staff.is_active
                staff.user.save(update_fields=["is_active"])

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

# ─────────────────────── invitation / onboarding ──────────────────────

@api_view(["GET"])
@permission_classes([AllowAny])
def verify_invitation(request):
    """
    GET /auth/invitation/verify/?token=<token>
    Validates the signed invitation token and returns basic staff info.
    Used by the Employee Portal to pre-fill the set-password form.
    """
    token = request.query_params.get("token", "").strip()
    if not token:
        return Response({"message": "token is required"}, status=400)

    staff_id, error = _verify_invite_token(token)
    if error:
        return Response({"message": error}, status=400)

    staff = Staff.objects.select_related("company").filter(id=staff_id).first()
    if staff is None:
        return Response({"message": "Staff record not found"}, status=404)

    if staff.user is not None:
        return Response({"message": "This invitation has already been accepted."}, status=400)

    return Response({
        "valid": True,
        "staff": {
            "id": staff.id,
            "full_name": staff.full_name,
            "email": staff.email,
            "company_name": staff.company.name,
            "department": staff.department,
            "designation": staff.designation,
        },
    })


@api_view(["POST"])
@permission_classes([AllowAny])
@transaction.atomic
def accept_invitation(request):
    """
    POST /auth/invitation/accept/
    Body: { "token": "<token>", "password": "<new_password>" }
    Creates a Django User, links it to Staff, and returns JWT tokens.
    """
    token = request.data.get("token", "").strip()
    password = request.data.get("password", "")

    if not token:
        return Response({"message": "token is required"}, status=400)
    if not password:
        return Response({"message": "password is required"}, status=400)

    staff_id, error = _verify_invite_token(token)
    if error:
        return Response({"message": error}, status=400)

    staff = Staff.objects.select_related("company", "user").filter(id=staff_id).first()
    if staff is None:
        return Response({"message": "Staff record not found"}, status=404)

    if staff.user is not None:
        return Response({"message": "This invitation has already been accepted."}, status=400)

    if not staff.is_active:
        return Response({"message": "Your account has been deactivated."}, status=403)

    if not staff.email:
        return Response({"message": "No email address on record. Contact your administrator."}, status=400)

    # Validate password strength
    try:
        from django.contrib.auth.password_validation import validate_password
        validate_password(password)
    except ValidationError as e:
        return Response({"message": " ".join(e.messages)}, status=400)

    # Create Django User
    from django.contrib.auth.models import User as DjangoUser
    email_lower = staff.email.lower()
    if DjangoUser.objects.filter(email__iexact=email_lower).exists():
        return Response({"message": "An account with this email already exists."}, status=400)

    user = DjangoUser.objects.create_user(
        username=email_lower,
        email=email_lower,
        password=password,
        first_name=staff.full_name,
        is_active=True,
    )
    staff.user = user
    staff.save(update_fields=["user"])

    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])

    return build_auth_response(user, "Account activated successfully", status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def resend_invitation(request, id):
    """
    POST /auth/staff/resend-invite/<id>/
    Management only. Regenerates and resends the invitation email.
    """
    company, err = company_or_error(request)
    if err:
        return err

    if not is_management_user(request.user):
        return Response({"message": "Permission denied. Management access required."}, status=403)

    staff = Staff.objects.select_related("company").filter(company=company, id=id).first()
    if staff is None:
        return Response({"message": "Staff not found"}, status=404)

    if staff.user is not None:
        return Response({"message": "This staff member has already accepted their invitation."}, status=400)

    if not staff.email:
        return Response({"message": "Staff has no email address. Update the staff record first."}, status=400)

    if not staff.is_active:
        return Response({"message": "Cannot resend invitation to a deactivated employee."}, status=400)

    try:
        token = _make_invite_token(staff.id)
        _send_invite_email(staff, token)
    except Exception as exc:
        return Response({"message": f"Failed to send email: {exc}"}, status=500)

    return Response({"message": "Invitation email resent successfully."})
