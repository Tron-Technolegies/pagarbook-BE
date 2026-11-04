import hashlib
import hmac
import secrets

from django.db import models
from django.utils import timezone

from authentication.models import Company


class Device(models.Model):
    """An attendance device (the Flutter app installed on a tablet/phone)."""

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="devices")
    name = models.CharField(max_length=255)
    device_id = models.CharField(max_length=100)  # id the Flutter app reports (unique per company)
    location = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- device credential (only a hash is stored) ---
    device_key_hash = models.CharField(max_length=64, blank=True, default="", editable=False)
    key_rotated_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_auth_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "device_id"],
                name="unique_device_id_per_company",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.device_id})"

    @staticmethod
    def _hash_key(raw):
        return hashlib.sha256(raw.encode()).hexdigest()

    def issue_new_key(self):
        """Generate a new key, store only its hash, return the raw key (show once)."""
        raw = secrets.token_urlsafe(32)
        self.device_key_hash = self._hash_key(raw)
        self.key_rotated_at = timezone.now()
        self.save(update_fields=["device_key_hash", "key_rotated_at", "updated_at"])
        return raw

    def check_key(self, raw):
        if not raw or not self.device_key_hash:
            return False
        return hmac.compare_digest(self.device_key_hash, self._hash_key(raw))
