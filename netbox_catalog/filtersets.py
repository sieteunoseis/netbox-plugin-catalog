import django_filters
from django.db.models import Q

from netbox.filtersets import NetBoxModelFilterSet

from .models import InstallationLog


class InstallationLogFilterSet(NetBoxModelFilterSet):
    """FilterSet for InstallationLog model."""

    q = django_filters.CharFilter(
        method="search",
        label="Search"
    )
    package_name = django_filters.CharFilter(
        lookup_expr="icontains"
    )
    action = django_filters.ChoiceFilter(
        choices=InstallationLog.Action.choices
    )
    status = django_filters.ChoiceFilter(
        choices=InstallationLog.Status.choices
    )

    class Meta:
        model = InstallationLog
        fields = ["package_name", "action", "status", "user"]

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(package_name__icontains=value) |
            Q(version__icontains=value) |
            Q(output__icontains=value) |
            Q(error__icontains=value)
        )
