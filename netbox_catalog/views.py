from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views import View

from netbox.views import generic

from .catalog_service import CatalogService
from .installer import PluginInstaller
from .models import InstallationLog
from .tables import InstallationLogTable
from .filtersets import InstallationLogFilterSet
from .forms import PluginFilterForm, InstallForm, InstallationLogFilterForm


class CatalogListView(PermissionRequiredMixin, View):
    """Browse available plugins."""

    permission_required = "netbox_catalog.view_installationlog"
    template_name = "netbox_catalog/catalog_list.html"

    def get(self, request):
        service = CatalogService()

        # Get show_uncurated setting
        show_uncurated = request.GET.get("show_uncurated", "true").lower() != "false"

        # Get all plugins
        plugins = service.get_all_plugins(include_uncurated=show_uncurated)

        # Apply filters
        category = request.GET.get("category")
        certification = request.GET.get("certification")
        status = request.GET.get("status")
        compatibility = request.GET.get("compatibility")
        search = request.GET.get("q")

        if category:
            plugins = [p for p in plugins if p.category == category]

        if certification:
            plugins = [p for p in plugins if p.certification == certification]

        if status == "installed":
            plugins = [p for p in plugins if p.installed_version]
        elif status == "not_installed":
            plugins = [p for p in plugins if not p.installed_version]
        elif status == "activated":
            plugins = [p for p in plugins if p.is_activated]
        elif status == "upgradable":
            plugins = [p for p in plugins if p.upgrade_available]

        if compatibility == "compatible":
            plugins = [p for p in plugins if p.is_compatible]
        elif compatibility == "incompatible":
            plugins = [p for p in plugins if not p.is_compatible]
        elif compatibility == "unknown":
            plugins = [p for p in plugins if p.compatibility_source == "unknown"]

        if search:
            search_lower = search.lower()
            plugins = [
                p for p in plugins
                if search_lower in p.name.lower()
                or search_lower in p.summary.lower()
                or search_lower in p.author.lower()
            ]

        # Sort: featured first, then by name
        plugins.sort(key=lambda p: (not p.featured, p.name.lower()))

        categories = service.get_categories()
        filter_form = PluginFilterForm(request.GET, categories=categories)

        return render(request, self.template_name, {
            "plugins": plugins,
            "categories": categories,
            "certification_levels": service.get_certification_levels(),
            "filter_form": filter_form,
            "total_count": len(plugins),
        })


class PluginDetailView(PermissionRequiredMixin, View):
    """View plugin details."""

    permission_required = "netbox_catalog.view_installationlog"
    template_name = "netbox_catalog/plugin_detail.html"

    def get(self, request, name):
        service = CatalogService()
        plugin = service.get_plugin(name)

        if not plugin:
            messages.error(request, f"Plugin '{name}' not found.")
            return redirect("plugins:netbox_catalog:catalog_list")

        # Get installation history for this plugin
        install_logs = InstallationLog.objects.filter(
            package_name=name
        ).order_by("-started")[:10]

        return render(request, self.template_name, {
            "plugin": plugin,
            "object": plugin,  # For breadcrumbs
            "install_logs": install_logs,
            "certification_levels": service.get_certification_levels(),
        })


class PluginInstallView(PermissionRequiredMixin, View):
    """Install a plugin."""

    permission_required = "netbox_catalog.add_installationlog"
    template_name = "netbox_catalog/plugin_install.html"

    def get(self, request, name):
        service = CatalogService()
        plugin = service.get_plugin(name)

        if not plugin:
            messages.error(request, f"Plugin '{name}' not found.")
            return redirect("plugins:netbox_catalog:catalog_list")

        installer = PluginInstaller()

        return render(request, self.template_name, {
            "plugin": plugin,
            "object": plugin,
            "form": InstallForm(initial={"version": plugin.version}),
            "config_snippet": installer.generate_config_snippet(name),
        })

    def post(self, request, name):
        service = CatalogService()
        plugin = service.get_plugin(name)

        if not plugin:
            messages.error(request, f"Plugin '{name}' not found.")
            return redirect("plugins:netbox_catalog:catalog_list")

        form = InstallForm(request.POST)
        installer = PluginInstaller()

        if not form.is_valid():
            return render(request, self.template_name, {
                "plugin": plugin,
                "object": plugin,
                "form": form,
                "config_snippet": installer.generate_config_snippet(name),
            })

        version = form.cleaned_data.get("version") or None
        upgrade = bool(plugin.installed_version)

        # Create log entry
        log = InstallationLog.objects.create(
            package_name=name,
            version=version or plugin.version,
            action=InstallationLog.Action.UPGRADE if upgrade else InstallationLog.Action.INSTALL,
            status=InstallationLog.Status.IN_PROGRESS,
            user=request.user,
        )

        # Perform installation
        result = installer.install(name, version=version, upgrade=upgrade)

        # Update log
        log.status = InstallationLog.Status.SUCCESS if result.success else InstallationLog.Status.FAILED
        log.output = result.output
        log.error = result.error
        log.version = result.version or version or plugin.version
        log.completed = timezone.now()
        log.save()

        if result.success:
            messages.success(request, f"Successfully installed {name} {result.version}")
            return redirect("plugins:netbox_catalog:plugin_installed", name=name)
        else:
            messages.error(request, f"Failed to install {name}: {result.error}")
            return render(request, self.template_name, {
                "plugin": plugin,
                "object": plugin,
                "form": form,
                "error": result.error,
                "output": result.output,
                "config_snippet": installer.generate_config_snippet(name),
            })


class PluginInstalledView(PermissionRequiredMixin, View):
    """Post-installation instructions."""

    permission_required = "netbox_catalog.view_installationlog"
    template_name = "netbox_catalog/plugin_installed.html"

    def get(self, request, name):
        service = CatalogService()
        plugin = service.get_plugin(name)
        installer = PluginInstaller()

        commands = installer.generate_post_install_commands()

        return render(request, self.template_name, {
            "plugin": plugin,
            "object": plugin,
            "config_snippet": installer.generate_config_snippet(name),
            "commands": commands,
        })


class InstallationLogListView(generic.ObjectListView):
    """View installation history."""

    queryset = InstallationLog.objects.all()
    table = InstallationLogTable
    filterset = InstallationLogFilterSet
    filterset_form = InstallationLogFilterForm
    template_name = "netbox_catalog/installationlog_list.html"


class InstallationLogView(generic.ObjectView):
    """View single installation log."""

    queryset = InstallationLog.objects.all()
    template_name = "netbox_catalog/installationlog.html"


class InstallationLogDeleteView(generic.ObjectDeleteView):
    """Delete installation log."""

    queryset = InstallationLog.objects.all()


class RefreshCacheView(PermissionRequiredMixin, View):
    """Refresh the catalog cache."""

    permission_required = "netbox_catalog.add_installationlog"

    def post(self, request):
        service = CatalogService()
        service.refresh_cache()
        messages.success(request, "Catalog cache refreshed.")
        return redirect("plugins:netbox_catalog:catalog_list")
