from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from ..models import InstallationLog


class InstallationLogSerializer(NetBoxModelSerializer):
    """Serializer for InstallationLog model."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_catalog-api:installationlog-detail"
    )

    class Meta:
        model = InstallationLog
        fields = [
            "id",
            "url",
            "display",
            "package_name",
            "version",
            "action",
            "status",
            "output",
            "error",
            "user",
            "started",
            "completed",
            "created",
            "last_updated",
        ]
        read_only_fields = ["user", "started", "completed"]
