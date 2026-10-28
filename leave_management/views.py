from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from authentication.models import Staff
from authentication.utils import is_management_user

from .models import LeaveType, LeaveRequest
from .serializers import (
    LeaveTypeSerializer,
    LeaveRequestSerializer,
    LeaveReviewSerializer,
)


VALID_STATUSES = {choice[0] for choice in LeaveRequest.STATUS_CHOICES}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_active_staff(user):
    """
    Return the active Staff profile and company for the authenticated user.
    Return None if the user has no active Staff profile.
    """
    try:
        staff = Staff.objects.select_related("company").get(user=user)
    except Staff.DoesNotExist:
        return None

    if not staff.is_active or not staff.company.is_active:
        return None

    return staff


def require_active_staff(request):
    """
    Return (staff, None) when the user has an active Staff profile.
    Otherwise return (None, error_response).
    """
    staff = get_active_staff(request.user)

    if staff is None:
        return None, Response(
            {"error": "Active staff profile required."},
            status=status.HTTP_403_FORBIDDEN,
        )

    return staff, None


def is_management(request):
    """
    Use the existing management permission utility.
    """
    try:
        return bool(is_management_user(request.user))
    except (AttributeError, Staff.DoesNotExist):
        return False


def bad_request(message):
    return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)


def parse_date_param(request, name):
    """
    Return (date_or_None, error_response_or_None) for a YYYY-MM-DD query param.
    """
    value = request.query_params.get(name)

    if not value:
        return None, None

    try:
        parsed = parse_date(value)
    except ValueError:
        parsed = None

    if parsed is None:
        return None, bad_request(f"{name} must be a valid date (YYYY-MM-DD).")

    return parsed, None


# ---------------------------------------------------------------------------
# Leave types
# ---------------------------------------------------------------------------

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_leave_type(request):
    staff, error_response = require_active_staff(request)

    if error_response:
        return error_response

    if not is_management(request):
        return Response(
            {"error": "Only authorized management users can create leave types."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = LeaveTypeSerializer(
        data=request.data,
        context={"company": staff.company},
    )

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            leave_type = serializer.save(company=staff.company)
    except IntegrityError:
        return bad_request("A leave type with this name already exists.")

    return Response(
        LeaveTypeSerializer(leave_type).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def view_leave_types(request):
    staff, error_response = require_active_staff(request)

    if error_response:
        return error_response

    leave_types = LeaveType.objects.filter(
        company=staff.company
    ).order_by("name")

    active = request.query_params.get("active")

    if active == "true":
        leave_types = leave_types.filter(is_active=True)
    elif active == "false":
        leave_types = leave_types.filter(is_active=False)
    elif active is not None:
        return bad_request("The active parameter must be true or false.")

    serializer = LeaveTypeSerializer(leave_types, many=True)

    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def view_single_leave_type(request, pk):
    staff, error_response = require_active_staff(request)

    if error_response:
        return error_response

    leave_type = get_object_or_404(
        LeaveType,
        pk=pk,
        company=staff.company,
    )

    return Response(
        LeaveTypeSerializer(leave_type).data,
        status=status.HTTP_200_OK,
    )


@api_view(["PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def update_leave_type(request, pk):
    staff, error_response = require_active_staff(request)

    if error_response:
        return error_response

    if not is_management(request):
        return Response(
            {"error": "Only authorized management users can update leave types."},
            status=status.HTTP_403_FORBIDDEN,
        )

    leave_type = get_object_or_404(
        LeaveType,
        pk=pk,
        company=staff.company,
    )

    serializer = LeaveTypeSerializer(
        leave_type,
        data=request.data,
        partial=(request.method == "PATCH"),
        context={"company": staff.company},
    )

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            leave_type = serializer.save()
    except IntegrityError:
        return bad_request("A leave type with this name already exists.")

    return Response(
        LeaveTypeSerializer(leave_type).data,
        status=status.HTTP_200_OK,
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_leave_type(request, pk):
    staff, error_response = require_active_staff(request)

    if error_response:
        return error_response

    if not is_management(request):
        return Response(
            {"error": "Only authorized management users can delete leave types."},
            status=status.HTTP_403_FORBIDDEN,
        )

    leave_type = get_object_or_404(
        LeaveType,
        pk=pk,
        company=staff.company,
    )

    try:
        leave_type.delete()
    except ProtectedError:
        return bad_request(
            "This leave type is associated with existing leave requests. "
            "Deactivate it instead of deleting it."
        )

    return Response(
        {"message": "Leave type deleted successfully."},
        status=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# Employee leave requests
# ---------------------------------------------------------------------------

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def apply_for_leave(request):
    staff, error_response = require_active_staff(request)

    if error_response:
        return error_response

    # The company in the context limits leave_type to this company's
    # active leave types.
    serializer = LeaveRequestSerializer(
        data=request.data,
        context={"company": staff.company},
    )

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    leave_request = LeaveRequest(
        company=staff.company,
        employee=staff,
        **serializer.validated_data,
    )

    try:
        leave_request.full_clean()
        leave_request.save()
    except ValidationError as exc:
        errors = (
            exc.message_dict
            if hasattr(exc, "message_dict")
            else exc.messages
        )

        return Response(
            {"error": errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        LeaveRequestSerializer(leave_request).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def view_leave_requests(request):
    """
    The logged-in employee's own leave requests.
    Optional filter: ?status=pending|approved|rejected|cancelled
    """
    staff, error_response = require_active_staff(request)

    if error_response:
        return error_response

    leave_requests = LeaveRequest.objects.filter(
        company=staff.company,
        employee=staff,
    ).select_related("employee", "leave_type", "reviewed_by")

    status_param = request.query_params.get("status")

    if status_param:
        if status_param not in VALID_STATUSES:
            return bad_request(
                "status must be one of: pending, approved, rejected, cancelled."
            )
        leave_requests = leave_requests.filter(status=status_param)

    serializer = LeaveRequestSerializer(leave_requests, many=True)

    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def view_single_leave_request(request, pk):
    """
    Employees can open their own requests. Management can open any request
    in their company.
    """
    staff, error_response = require_active_staff(request)

    if error_response:
        return error_response

    leave_request = get_object_or_404(
        LeaveRequest.objects.select_related(
            "employee", "leave_type", "reviewed_by"
        ),
        pk=pk,
        company=staff.company,
    )

    if not is_management(request) and leave_request.employee_id != staff.id:
        return Response(
            {"detail": "Not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(
        LeaveRequestSerializer(leave_request).data,
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_leave_request(request, pk):
    """
    An employee cancels their own request while it is still pending.
    """
    staff, error_response = require_active_staff(request)

    if error_response:
        return error_response

    with transaction.atomic():
        leave_request = get_object_or_404(
            LeaveRequest.objects.select_for_update(),
            pk=pk,
            company=staff.company,
            employee=staff,
        )

        if leave_request.status != "pending":
            return bad_request(
                "Only pending leave requests can be cancelled. "
                f"Current status: {leave_request.status}."
            )

        leave_request.status = "cancelled"
        leave_request.save(update_fields=["status", "updated_at"])

    return Response(
        LeaveRequestSerializer(leave_request).data,
        status=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# Management: list, approve, reject
# ---------------------------------------------------------------------------

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def manage_leave_requests(request):
    """
    All leave requests in the manager's company.
    Optional filters: status, employee (id), leave_type (id),
    from_date and to_date (YYYY-MM-DD, matches requests overlapping the range).
    """
    staff, error_response = require_active_staff(request)

    if error_response:
        return error_response

    if not is_management(request):
        return Response(
            {"error": "Only authorized management users can view all leave requests."},
            status=status.HTTP_403_FORBIDDEN,
        )

    leave_requests = LeaveRequest.objects.filter(
        company=staff.company
    ).select_related("employee", "leave_type", "reviewed_by")

    status_param = request.query_params.get("status")

    if status_param:
        if status_param not in VALID_STATUSES:
            return bad_request(
                "status must be one of: pending, approved, rejected, cancelled."
            )
        leave_requests = leave_requests.filter(status=status_param)

    employee_id = request.query_params.get("employee")

    if employee_id:
        if not employee_id.isdigit():
            return bad_request("employee must be a numeric id.")
        leave_requests = leave_requests.filter(employee_id=int(employee_id))

    leave_type_id = request.query_params.get("leave_type")

    if leave_type_id:
        if not leave_type_id.isdigit():
            return bad_request("leave_type must be a numeric id.")
        leave_requests = leave_requests.filter(leave_type_id=int(leave_type_id))

    from_date, error_response = parse_date_param(request, "from_date")

    if error_response:
        return error_response

    to_date, error_response = parse_date_param(request, "to_date")

    if error_response:
        return error_response

    if from_date:
        leave_requests = leave_requests.filter(end_date__gte=from_date)

    if to_date:
        leave_requests = leave_requests.filter(start_date__lte=to_date)

    serializer = LeaveRequestSerializer(leave_requests, many=True)

    return Response(serializer.data, status=status.HTTP_200_OK)


def review_leave_request(request, pk, new_status):
    """
    Shared logic for approve and reject. Only pending requests can be reviewed.
    """
    staff, error_response = require_active_staff(request)

    if error_response:
        return error_response

    if not is_management(request):
        return Response(
            {"error": "Only authorized management users can review leave requests."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = LeaveReviewSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    review_comment = serializer.validated_data.get("review_comment", "").strip()

    if new_status == "rejected" and not review_comment:
        return Response(
            {"review_comment": ["A comment is required when rejecting a request."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        # Lock the row so two reviewers cannot act on the same request.
        leave_request = get_object_or_404(
            LeaveRequest.objects.select_for_update(),
            pk=pk,
            company=staff.company,
        )

        if leave_request.status != "pending":
            return bad_request(
                "Only pending leave requests can be reviewed. "
                f"Current status: {leave_request.status}."
            )

        leave_request.status = new_status
        leave_request.reviewed_by = staff
        leave_request.review_comment = review_comment
        leave_request.reviewed_at = timezone.now()
        leave_request.save(
            update_fields=[
                "status",
                "reviewed_by",
                "review_comment",
                "reviewed_at",
                "updated_at",
            ]
        )

    return Response(
        LeaveRequestSerializer(leave_request).data,
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def approve_leave_request(request, pk):
    return review_leave_request(request, pk, "approved")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def reject_leave_request(request, pk):
    return review_leave_request(request, pk, "rejected")