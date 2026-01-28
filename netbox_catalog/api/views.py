from netbox.api.viewsets import NetBoxModelViewSet

from ..filtersets import InstallationLogFilterSet
from ..models import InstallationLog
from .serializers import InstallationLogSerializer


class InstallationLogViewSet(NetBoxModelViewSet):
    """API viewset for InstallationLog model."""

    queryset = InstallationLog.objects.all()
    serializer_class = InstallationLogSerializer
    filterset_class = InstallationLogFilterSet
