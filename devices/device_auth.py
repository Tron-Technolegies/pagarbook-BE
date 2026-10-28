from datetime import timedelta

from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.permissions import BasePermission
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import Token

from .models import Device


class DeviceAccessToken(Token):
    """Signed token for kiosks. Has its own token_type, so staff JWTs are not accepted here
    and device tokens are not accepted by the staff JWTAuthentication."""
    token_type = "device"
    lifetime = timedelta(hours=12)


def _key_stamp(device):
    """Changes whenever the device key is regenerated, which invalidates old tokens."""
    return int(device.key_rotated_at.timestamp()) if device.key_rotated_at else 0


def make_device_token(device):
    token = DeviceAccessToken()
    token["device_pk"] = device.pk
    token["kr"] = _key_stamp(device)
    return str(token)


class DeviceUser:
    """Minimal stand-in for request.user on kiosk requests."""
    is_authenticated = True
    is_anonymous = False

    def __init__(self, device):
        self.device = device
        self.company = device.company


class DeviceAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != b"bearer":
            return None
        if len(parts) != 2:
            raise exceptions.AuthenticationFailed("Invalid Authorization header.")

        try:
            # verifies signature, expiry and token_type
            token = DeviceAccessToken(parts[1].decode())
        except (TokenError, UnicodeDecodeError):
            raise exceptions.AuthenticationFailed("Invalid or expired device token.")

        try:
            device = Device.objects.select_related("company").get(pk=token["device_pk"])
        except (Device.DoesNotExist, KeyError):
            raise exceptions.AuthenticationFailed("Invalid device token.")

        if token.get("kr") != _key_stamp(device):
            raise exceptions.AuthenticationFailed("Device key was changed. Re-authenticate.")

        # checked on every request, so deactivation takes effect immediately
        if not device.is_active or not device.company.is_active:
            raise exceptions.PermissionDenied("Device is inactive.")

        return (DeviceUser(device), token)


class IsDevice(BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.user, DeviceUser)