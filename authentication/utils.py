from rest_framework.response import Response


def company_or_error(request):
    """Returns (company, None), or (None, error Response) if the caller has no active company."""
    staff = getattr(request.user, "staff", None)
    if staff is None:
        return None, Response({"message": "Staff record not found"}, status=404)
    if not staff.is_active:
        return None, Response({"message": "Your account has been deactivated."}, status=403)
    if not staff.company.is_active:
        return None, Response({"message": "Your company has been deactivated."}, status=403)
    return staff.company, None


def validation_error(serializer):
    first = next(iter(serializer.errors.values()))[0]
    return Response({"message": str(first), "errors": serializer.errors}, status=400)


def is_management_user(user):
    """Checks if the user belongs to Management department or has Django staff/superuser privileges."""
    staff = getattr(user, "staff", None)
    if not staff:
        return False
    return (
        staff.department == "Management"
        or getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
    )