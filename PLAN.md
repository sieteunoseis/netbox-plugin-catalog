# NetBox Plugin Catalog Implementation Plan

## Overview

Create a NetBox plugin `netbox-catalog` that provides an in-app catalog of third-party NetBox plugins. Users can browse available plugins, view metadata, check compatibility, and install packages directly from the UI. After pip installation, users must manually add the plugin to their configuration and restart NetBox.

## Design Decisions

Based on user requirements:
- **Installation Level**: Catalog + pip install (user manually edits config and restarts)
- **Data Source**: PyPI auto-discovery + curated JSON overlay for quality/compatibility info
- **Deployment**: NetBox plugin only (no separate website)

## Key Features

1. **Plugin Discovery**
   - Auto-discover `netbox-*` packages from PyPI
   - Display rich metadata (version, description, author, license, dependencies)
   - Show Python and NetBox version compatibility

2. **Curated Catalog Overlay**
   - JSON file with curated plugin info (compatibility ratings, categories, notes)
   - Can mark plugins as certified, compatible, deprecated, or not recommended
   - Add categories/tags beyond what PyPI provides

3. **Installation Status**
   - Detect which plugins are installed (via pip)
   - Detect which plugins are activated (in PLUGINS list)
   - Show upgrade available when new version exists

4. **One-Click Install**
   - Run `pip install <package>` from the UI
   - Show installation progress/output
   - Generate config snippet for `configuration.py`
   - Show migration command

5. **Plugin Details**
   - Full description/README
   - Version history
   - Links to repository, documentation, issues
   - Dependency information

## Architecture

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        NetBox Catalog Plugin                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐ │
│  │   PyPI API   │───▶│  Catalog     │◀───│  Curated JSON        │ │
│  │   (discover) │    │  Service     │    │  (compatibility)     │ │
│  └──────────────┘    └──────────────┘    └──────────────────────┘ │
│                             │                                       │
│                             ▼                                       │
│                      ┌──────────────┐                              │
│                      │   Cache      │                              │
│                      │   (Django)   │                              │
│                      └──────────────┘                              │
│                             │                                       │
│         ┌───────────────────┼───────────────────┐                  │
│         ▼                   ▼                   ▼                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐        │
│  │  List View   │    │ Detail View  │    │ Install View │        │
│  │  (browse)    │    │ (metadata)   │    │ (pip action) │        │
│  └──────────────┘    └──────────────┘    └──────────────┘        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Plugin Structure

```
~/development/netbox-catalog/
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── catalog.json                    # Curated plugin metadata (can be updated independently)
├── netbox_catalog/
│   ├── __init__.py                 # Plugin config
│   ├── pypi_client.py              # PyPI API client with caching
│   ├── catalog_service.py          # Merges PyPI + curated data
│   ├── installer.py                # pip install wrapper
│   ├── compatibility.py            # NetBox version compatibility checker
│   ├── models.py                   # InstallationLog model
│   ├── views.py                    # Catalog views
│   ├── tables.py                   # Plugin list table
│   ├── filtersets.py               # Filter by category, status
│   ├── forms.py                    # Install form, filter form
│   ├── urls.py                     # URL routing
│   ├── navigation.py               # Plugin menu
│   ├── api/
│   │   ├── __init__.py
│   │   ├── views.py                # API endpoints
│   │   ├── serializers.py
│   │   └── urls.py
│   └── templates/netbox_catalog/
│       ├── catalog_list.html       # Plugin browser
│       ├── plugin_detail.html      # Plugin detail page
│       ├── plugin_install.html     # Install confirmation/progress
│       ├── plugin_installed.html   # Post-install instructions
│       └── inc/
│           ├── _plugin_card.html   # Plugin card component
│           └── _status_badge.html  # Install status badge
```

## Implementation Details

### 1. Plugin Configuration (`__init__.py`)

```python
from netbox.plugins import PluginConfig

class NetBoxCatalogConfig(PluginConfig):
    name = "netbox_catalog"
    verbose_name = "Plugin Catalog"
    description = "Browse and install third-party NetBox plugins"
    version = "0.1.0"
    author = "Your Name"
    author_email = "your.email@example.com"
    base_url = "catalog"
    min_version = "4.0.0"

    default_settings = {
        "pypi_cache_timeout": 3600,       # Cache PyPI data for 1 hour
        "catalog_json_url": "",            # Optional: remote catalog.json URL
        "allow_install": True,             # Enable/disable pip install feature
        "show_uncurated": True,            # Show plugins not in curated list
        "pypi_index_url": "https://pypi.org",  # PyPI mirror support
    }

config = NetBoxCatalogConfig
```

### 2. PyPI Client (`pypi_client.py`)

```python
import requests
from django.core.cache import cache
from django.conf import settings
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class PyPIClient:
    """Client for fetching NetBox plugins from PyPI."""

    SIMPLE_API = "/simple/"
    JSON_API = "/pypi/{package}/json"
    NETBOX_PREFIXES = ["netbox-", "netbox_"]

    def __init__(self, base_url: str = "https://pypi.org", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.pypi.simple.v1+json",
            "User-Agent": "netbox-catalog/0.1.0"
        })

    def get_all_netbox_packages(self) -> list[str]:
        """Fetch all package names that start with netbox- prefix."""
        cache_key = "pypi_netbox_packages"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            response = self.session.get(
                f"{self.base_url}{self.SIMPLE_API}",
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()

            # Filter for netbox-* packages
            packages = [
                p["name"] for p in data.get("projects", [])
                if any(p["name"].lower().startswith(prefix) for prefix in self.NETBOX_PREFIXES)
            ]

            cache_timeout = getattr(settings, 'PLUGINS_CONFIG', {}).get(
                'netbox_catalog', {}
            ).get('pypi_cache_timeout', 3600)
            cache.set(cache_key, packages, cache_timeout)

            return packages

        except requests.RequestException as e:
            logger.error(f"Failed to fetch PyPI package list: {e}")
            return []

    def get_package_info(self, package_name: str) -> Optional[dict]:
        """Fetch detailed package info from PyPI JSON API."""
        cache_key = f"pypi_package_{package_name}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            url = f"{self.base_url}{self.JSON_API.format(package=package_name)}"
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            # Extract relevant info
            info = data.get("info", {})
            package_info = {
                "name": info.get("name"),
                "version": info.get("version"),
                "summary": info.get("summary"),
                "description": info.get("description"),
                "description_content_type": info.get("description_content_type"),
                "author": info.get("author") or self._extract_author_from_email(info.get("author_email")),
                "author_email": info.get("author_email"),
                "license": info.get("license"),
                "keywords": info.get("keywords"),
                "classifiers": info.get("classifiers", []),
                "requires_python": info.get("requires_python"),
                "requires_dist": info.get("requires_dist", []),
                "project_urls": info.get("project_urls", {}),
                "home_page": info.get("home_page") or info.get("project_urls", {}).get("Homepage"),
                "releases": list(data.get("releases", {}).keys()),
            }

            # Extract NetBox version compatibility from classifiers
            package_info["netbox_compatibility"] = self._extract_netbox_compatibility(
                info.get("classifiers", [])
            )

            cache_timeout = getattr(settings, 'PLUGINS_CONFIG', {}).get(
                'netbox_catalog', {}
            ).get('pypi_cache_timeout', 3600)
            cache.set(cache_key, package_info, cache_timeout)

            return package_info

        except requests.RequestException as e:
            logger.error(f"Failed to fetch package info for {package_name}: {e}")
            return None

    def _extract_author_from_email(self, email_field: str) -> str:
        """Extract author name from 'Name <email>' format."""
        if not email_field:
            return ""
        if "<" in email_field:
            return email_field.split("<")[0].strip()
        return email_field

    def _extract_netbox_compatibility(self, classifiers: list) -> list[str]:
        """Extract NetBox version compatibility from classifiers."""
        # Look for Framework :: NetBox :: X.Y classifiers
        netbox_versions = []
        for classifier in classifiers:
            if classifier.startswith("Framework :: NetBox ::"):
                version = classifier.split("::")[-1].strip()
                netbox_versions.append(version)
        return netbox_versions
```

### 3. Curated Catalog Schema (`catalog.json`)

```json
{
    "version": "1.0.0",
    "last_updated": "2026-01-28",
    "plugins": {
        "netbox-bgp": {
            "category": "Network Management",
            "tags": ["routing", "bgp"],
            "certification": "certified",
            "netbox_min_version": "4.0.0",
            "netbox_max_version": null,
            "notes": "Official BGP plugin maintained by NetBox Labs",
            "recommended": true,
            "documentation_url": "https://github.com/netbox-community/netbox-bgp",
            "featured": true
        },
        "netbox-acls": {
            "category": "Security",
            "tags": ["acl", "firewall", "access-lists"],
            "certification": "compatible",
            "netbox_min_version": "4.0.0",
            "notes": "Access Control List management",
            "recommended": true
        },
        "netbox-old-plugin": {
            "category": "Deprecated",
            "certification": "deprecated",
            "notes": "No longer maintained, use netbox-new-plugin instead",
            "recommended": false,
            "replacement": "netbox-new-plugin"
        }
    },
    "categories": [
        "Network Management",
        "Security",
        "Monitoring",
        "Documentation",
        "Automation",
        "Infrastructure",
        "Integration",
        "Other"
    ],
    "certification_levels": {
        "certified": {
            "label": "Certified",
            "description": "Certified by NetBox Labs, guaranteed compatibility",
            "color": "success"
        },
        "compatible": {
            "label": "Compatible",
            "description": "Community validated, works with current NetBox",
            "color": "info"
        },
        "untested": {
            "label": "Untested",
            "description": "Not tested with current NetBox version",
            "color": "warning"
        },
        "deprecated": {
            "label": "Deprecated",
            "description": "No longer maintained or recommended",
            "color": "danger"
        }
    }
}
```

### 4. Catalog Service (`catalog_service.py`)

```python
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
import subprocess
import sys

from django.core.cache import cache
from django.conf import settings
import requests

from .pypi_client import PyPIClient


@dataclass
class PluginInfo:
    """Combined plugin information from PyPI and curated catalog."""
    name: str
    version: str
    summary: str = ""
    description: str = ""
    author: str = ""
    license: str = ""
    keywords: list = field(default_factory=list)
    home_page: str = ""
    project_urls: dict = field(default_factory=dict)
    requires_python: str = ""
    requires_dist: list = field(default_factory=list)
    releases: list = field(default_factory=list)

    # From curated catalog
    category: str = "Other"
    tags: list = field(default_factory=list)
    certification: str = "untested"
    netbox_min_version: str = ""
    netbox_max_version: str = ""
    notes: str = ""
    recommended: bool = True
    featured: bool = False
    documentation_url: str = ""
    replacement: str = ""

    # Runtime status
    installed_version: str = ""
    is_activated: bool = False
    upgrade_available: bool = False

    # Compatibility status (computed)
    is_compatible: bool = True
    compatibility_reason: str = ""
    compatibility_source: str = "unknown"  # curated, plugin_config, readme, unknown


class CatalogService:
    """Service for managing the plugin catalog."""

    def __init__(self):
        self.pypi_client = PyPIClient()
        self._curated_data = None

    @property
    def curated_data(self) -> dict:
        """Load curated catalog data."""
        if self._curated_data is None:
            self._curated_data = self._load_curated_catalog()
        return self._curated_data

    def _load_curated_catalog(self) -> dict:
        """Load curated catalog from file or URL."""
        # Try remote URL first
        config = getattr(settings, 'PLUGINS_CONFIG', {}).get('netbox_catalog', {})
        remote_url = config.get('catalog_json_url')

        if remote_url:
            try:
                response = requests.get(remote_url, timeout=30)
                response.raise_for_status()
                return response.json()
            except requests.RequestException:
                pass

        # Fall back to local file
        catalog_path = Path(__file__).parent.parent / "catalog.json"
        if catalog_path.exists():
            with open(catalog_path) as f:
                return json.load(f)

        return {"plugins": {}, "categories": [], "certification_levels": {}}

    def get_all_plugins(self, include_uncurated: bool = True) -> list[PluginInfo]:
        """Get all available plugins with merged metadata."""
        plugins = []

        # Get all netbox packages from PyPI
        package_names = self.pypi_client.get_all_netbox_packages()

        # Get installed packages
        installed = self._get_installed_packages()
        activated = self._get_activated_plugins()

        for name in package_names:
            # Check if should show uncurated plugins
            curated_info = self.curated_data.get("plugins", {}).get(name, {})
            if not include_uncurated and not curated_info:
                continue

            # Get PyPI info
            pypi_info = self.pypi_client.get_package_info(name)
            if not pypi_info:
                continue

            # Merge into PluginInfo
            plugin = self._merge_plugin_info(name, pypi_info, curated_info)

            # Add runtime status
            if name in installed:
                plugin.installed_version = installed[name]
                plugin.upgrade_available = plugin.version != installed[name]

            # Check module name variations for activation
            module_name = name.replace("-", "_")
            plugin.is_activated = module_name in activated

            plugins.append(plugin)

        return plugins

    def get_plugin(self, name: str) -> Optional[PluginInfo]:
        """Get a single plugin's information."""
        pypi_info = self.pypi_client.get_package_info(name)
        if not pypi_info:
            return None

        curated_info = self.curated_data.get("plugins", {}).get(name, {})
        plugin = self._merge_plugin_info(name, pypi_info, curated_info)

        # Add runtime status
        installed = self._get_installed_packages()
        activated = self._get_activated_plugins()

        if name in installed:
            plugin.installed_version = installed[name]
            plugin.upgrade_available = plugin.version != installed[name]

        module_name = name.replace("-", "_")
        plugin.is_activated = module_name in activated

        return plugin

    def _merge_plugin_info(self, name: str, pypi_info: dict, curated_info: dict) -> PluginInfo:
        """Merge PyPI and curated data into PluginInfo."""
        return PluginInfo(
            name=name,
            version=pypi_info.get("version", ""),
            summary=pypi_info.get("summary", ""),
            description=pypi_info.get("description", ""),
            author=pypi_info.get("author", ""),
            license=pypi_info.get("license", ""),
            keywords=pypi_info.get("keywords", "").split(",") if pypi_info.get("keywords") else [],
            home_page=pypi_info.get("home_page", ""),
            project_urls=pypi_info.get("project_urls", {}),
            requires_python=pypi_info.get("requires_python", ""),
            requires_dist=pypi_info.get("requires_dist", []),
            releases=pypi_info.get("releases", []),

            # Curated overrides
            category=curated_info.get("category", "Other"),
            tags=curated_info.get("tags", []),
            certification=curated_info.get("certification", "untested"),
            netbox_min_version=curated_info.get("netbox_min_version", ""),
            netbox_max_version=curated_info.get("netbox_max_version", ""),
            notes=curated_info.get("notes", ""),
            recommended=curated_info.get("recommended", True),
            featured=curated_info.get("featured", False),
            documentation_url=curated_info.get("documentation_url", ""),
            replacement=curated_info.get("replacement", ""),
        )

    def _get_installed_packages(self) -> dict[str, str]:
        """Get dict of installed package names to versions."""
        cache_key = "installed_packages"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--format=json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                packages = json.loads(result.stdout)
                installed = {p["name"]: p["version"] for p in packages}
                cache.set(cache_key, installed, 60)  # Cache for 1 minute
                return installed
        except (subprocess.SubprocessError, json.JSONDecodeError):
            pass

        return {}

    def _get_activated_plugins(self) -> list[str]:
        """Get list of activated plugin module names."""
        return list(getattr(settings, 'PLUGINS', []))

    def get_categories(self) -> list[str]:
        """Get list of available categories."""
        return self.curated_data.get("categories", [])

    def get_certification_levels(self) -> dict:
        """Get certification level definitions."""
        return self.curated_data.get("certification_levels", {})

    def refresh_cache(self):
        """Clear cached data to force refresh."""
        cache.delete("pypi_netbox_packages")
        cache.delete("installed_packages")
        # Clear individual package caches would require tracking keys
        self._curated_data = None
```

### 5. Installer (`installer.py`)

```python
import subprocess
import sys
import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class InstallResult:
    """Result of a pip install operation."""
    success: bool
    package_name: str
    version: str = ""
    output: str = ""
    error: str = ""


class PluginInstaller:
    """Handles pip installation of plugins."""

    def __init__(self, timeout: int = 300):
        self.timeout = timeout

    def install(self, package_name: str, version: str = None, upgrade: bool = False) -> InstallResult:
        """Install a package using pip."""
        package_spec = f"{package_name}=={version}" if version else package_name

        cmd = [sys.executable, "-m", "pip", "install"]
        if upgrade:
            cmd.append("--upgrade")
        cmd.append(package_spec)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )

            if result.returncode == 0:
                installed_version = self._get_installed_version(package_name)
                return InstallResult(
                    success=True,
                    package_name=package_name,
                    version=installed_version,
                    output=result.stdout
                )
            else:
                return InstallResult(
                    success=False,
                    package_name=package_name,
                    output=result.stdout,
                    error=result.stderr
                )

        except subprocess.TimeoutExpired:
            return InstallResult(
                success=False,
                package_name=package_name,
                error=f"Installation timed out after {self.timeout} seconds"
            )
        except Exception as e:
            return InstallResult(
                success=False,
                package_name=package_name,
                error=str(e)
            )

    def uninstall(self, package_name: str) -> InstallResult:
        """Uninstall a package using pip."""
        cmd = [sys.executable, "-m", "pip", "uninstall", "-y", package_name]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            return InstallResult(
                success=result.returncode == 0,
                package_name=package_name,
                output=result.stdout,
                error=result.stderr if result.returncode != 0 else ""
            )

        except Exception as e:
            return InstallResult(
                success=False,
                package_name=package_name,
                error=str(e)
            )

    def _get_installed_version(self, package_name: str) -> str:
        """Get the installed version of a package."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "show", package_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if line.startswith("Version:"):
                        return line.split(":", 1)[1].strip()
        except Exception:
            pass
        return ""

    def generate_config_snippet(self, package_name: str) -> str:
        """Generate the configuration.py snippet for a plugin."""
        module_name = package_name.replace("-", "_")
        return f'''\
# Add to PLUGINS list in configuration.py:
PLUGINS = [
    # ... existing plugins ...
    "{module_name}",
]

# Add plugin configuration (if needed):
PLUGINS_CONFIG = {{
    # ... existing config ...
    "{module_name}": {{
        # Plugin-specific settings here
    }},
}}
'''

    def generate_migration_command(self) -> str:
        """Generate the migration command."""
        return "python manage.py migrate"

    def generate_collectstatic_command(self) -> str:
        """Generate the collectstatic command."""
        return "python manage.py collectstatic --no-input"
```

### 6. Models (`models.py`)

```python
from django.db import models
from django.contrib.auth import get_user_model

from netbox.models import NetBoxModel


class InstallationLog(NetBoxModel):
    """Log of plugin installation attempts."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In Progress"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    class Action(models.TextChoices):
        INSTALL = "install", "Install"
        UPGRADE = "upgrade", "Upgrade"
        UNINSTALL = "uninstall", "Uninstall"

    package_name = models.CharField(max_length=255)
    version = models.CharField(max_length=50, blank=True)
    action = models.CharField(max_length=20, choices=Action.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    output = models.TextField(blank=True)
    error = models.TextField(blank=True)
    user = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    started = models.DateTimeField(auto_now_add=True)
    completed = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started"]
        verbose_name = "Installation Log"
        verbose_name_plural = "Installation Logs"

    def __str__(self):
        return f"{self.action} {self.package_name} ({self.status})"
```

### 7. Views (`views.py`)

```python
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views import View
from django.utils import timezone
from django.contrib.auth.mixins import PermissionRequiredMixin

from netbox.views import generic

from .catalog_service import CatalogService
from .installer import PluginInstaller
from .models import InstallationLog
from .tables import PluginTable
from .filtersets import PluginFilterSet
from .forms import PluginFilterForm, InstallForm


class CatalogListView(PermissionRequiredMixin, View):
    """Browse available plugins."""
    permission_required = "netbox_catalog.view_installationlog"
    template_name = "netbox_catalog/catalog_list.html"

    def get(self, request):
        service = CatalogService()

        # Get all plugins
        plugins = service.get_all_plugins(
            include_uncurated=request.GET.get("show_uncurated", "true").lower() == "true"
        )

        # Apply filters
        category = request.GET.get("category")
        certification = request.GET.get("certification")
        status = request.GET.get("status")
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

        return render(request, self.template_name, {
            "plugins": plugins,
            "categories": service.get_categories(),
            "certification_levels": service.get_certification_levels(),
            "filter_form": PluginFilterForm(request.GET),
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
        if not form.is_valid():
            return render(request, self.template_name, {
                "plugin": plugin,
                "form": form,
            })

        version = form.cleaned_data.get("version") or plugin.version
        upgrade = bool(plugin.installed_version)

        # Create log entry
        log = InstallationLog.objects.create(
            package_name=name,
            version=version,
            action=InstallationLog.Action.UPGRADE if upgrade else InstallationLog.Action.INSTALL,
            status=InstallationLog.Status.IN_PROGRESS,
            user=request.user,
        )

        # Perform installation
        installer = PluginInstaller()
        result = installer.install(name, version=version, upgrade=upgrade)

        # Update log
        log.status = InstallationLog.Status.SUCCESS if result.success else InstallationLog.Status.FAILED
        log.output = result.output
        log.error = result.error
        log.version = result.version
        log.completed = timezone.now()
        log.save()

        if result.success:
            messages.success(request, f"Successfully installed {name} {result.version}")
            return redirect("plugins:netbox_catalog:plugin_installed", name=name)
        else:
            messages.error(request, f"Failed to install {name}: {result.error}")
            return render(request, self.template_name, {
                "plugin": plugin,
                "form": form,
                "error": result.error,
                "output": result.output,
            })


class PluginInstalledView(PermissionRequiredMixin, View):
    """Post-installation instructions."""
    permission_required = "netbox_catalog.view_installationlog"
    template_name = "netbox_catalog/plugin_installed.html"

    def get(self, request, name):
        service = CatalogService()
        plugin = service.get_plugin(name)
        installer = PluginInstaller()

        return render(request, self.template_name, {
            "plugin": plugin,
            "config_snippet": installer.generate_config_snippet(name),
            "migrate_command": installer.generate_migration_command(),
            "collectstatic_command": installer.generate_collectstatic_command(),
        })


class InstallationLogListView(generic.ObjectListView):
    """View installation history."""
    queryset = InstallationLog.objects.all()
    table = "netbox_catalog.InstallationLogTable"
    template_name = "netbox_catalog/installationlog_list.html"


class RefreshCacheView(PermissionRequiredMixin, View):
    """Refresh the catalog cache."""
    permission_required = "netbox_catalog.add_installationlog"

    def post(self, request):
        service = CatalogService()
        service.refresh_cache()
        messages.success(request, "Catalog cache refreshed.")
        return redirect("plugins:netbox_catalog:catalog_list")
```

### 8. Forms (`forms.py`)

```python
from django import forms


class PluginFilterForm(forms.Form):
    """Filter form for plugin catalog."""
    q = forms.CharField(
        required=False,
        label="Search",
        widget=forms.TextInput(attrs={"placeholder": "Search plugins..."})
    )
    category = forms.ChoiceField(required=False, choices=[])
    certification = forms.ChoiceField(
        required=False,
        choices=[
            ("", "All"),
            ("certified", "Certified"),
            ("compatible", "Compatible"),
            ("untested", "Untested"),
            ("deprecated", "Deprecated"),
        ]
    )
    status = forms.ChoiceField(
        required=False,
        choices=[
            ("", "All"),
            ("installed", "Installed"),
            ("not_installed", "Not Installed"),
            ("activated", "Activated"),
            ("upgradable", "Upgrade Available"),
        ]
    )
    show_uncurated = forms.BooleanField(required=False, initial=True)


class InstallForm(forms.Form):
    """Form for installing a plugin."""
    version = forms.CharField(
        required=False,
        label="Version",
        help_text="Leave empty to install latest version"
    )
    confirm = forms.BooleanField(
        required=True,
        label="I understand that I need to edit configuration.py and restart NetBox"
    )
```

### 9. Tables (`tables.py`)

```python
import django_tables2 as tables

from .models import InstallationLog


class InstallationLogTable(tables.Table):
    """Table for installation logs."""
    package_name = tables.Column(linkify=True)
    action = tables.Column()
    status = tables.Column()
    user = tables.Column()
    started = tables.DateTimeColumn()
    completed = tables.DateTimeColumn()

    class Meta:
        model = InstallationLog
        fields = ("package_name", "version", "action", "status", "user", "started", "completed")
```

### 10. URLs (`urls.py`)

```python
from django.urls import path

from . import views

urlpatterns = [
    path("", views.CatalogListView.as_view(), name="catalog_list"),
    path("refresh/", views.RefreshCacheView.as_view(), name="refresh_cache"),
    path("history/", views.InstallationLogListView.as_view(), name="installationlog_list"),
    path("plugin/<str:name>/", views.PluginDetailView.as_view(), name="plugin_detail"),
    path("plugin/<str:name>/install/", views.PluginInstallView.as_view(), name="plugin_install"),
    path("plugin/<str:name>/installed/", views.PluginInstalledView.as_view(), name="plugin_installed"),
]
```

### 11. Navigation (`navigation.py`)

```python
from netbox.plugins import PluginMenu, PluginMenuItem, PluginMenuButton

menu = PluginMenu(
    label="Plugin Catalog",
    groups=(
        ("Catalog", (
            PluginMenuItem(
                link="plugins:netbox_catalog:catalog_list",
                link_text="Browse Plugins",
                permissions=["netbox_catalog.view_installationlog"],
            ),
            PluginMenuItem(
                link="plugins:netbox_catalog:installationlog_list",
                link_text="Installation History",
                permissions=["netbox_catalog.view_installationlog"],
            ),
        )),
    ),
    icon_class="mdi mdi-puzzle",
)
```

### 12. Templates

#### `catalog_list.html`

```html
{% extends 'base/layout.html' %}
{% load helpers %}

{% block title %}Plugin Catalog{% endblock %}

{% block content %}
<div class="row mb-3">
    <div class="col-md-12">
        <div class="card">
            <div class="card-header d-flex justify-content-between align-items-center">
                <h5 class="mb-0">Plugin Catalog</h5>
                <div>
                    <span class="text-muted me-3">{{ total_count }} plugins</span>
                    <form method="post" action="{% url 'plugins:netbox_catalog:refresh_cache' %}" class="d-inline">
                        {% csrf_token %}
                        <button type="submit" class="btn btn-sm btn-outline-secondary">
                            <i class="mdi mdi-refresh"></i> Refresh
                        </button>
                    </form>
                </div>
            </div>
            <div class="card-body">
                <!-- Filters -->
                <form method="get" class="row g-3 mb-4">
                    <div class="col-md-3">
                        <input type="text" name="q" class="form-control"
                               placeholder="Search..." value="{{ request.GET.q }}">
                    </div>
                    <div class="col-md-2">
                        <select name="category" class="form-select">
                            <option value="">All Categories</option>
                            {% for cat in categories %}
                            <option value="{{ cat }}" {% if request.GET.category == cat %}selected{% endif %}>
                                {{ cat }}
                            </option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="col-md-2">
                        <select name="certification" class="form-select">
                            <option value="">All Certifications</option>
                            {% for key, level in certification_levels.items %}
                            <option value="{{ key }}" {% if request.GET.certification == key %}selected{% endif %}>
                                {{ level.label }}
                            </option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="col-md-2">
                        <select name="status" class="form-select">
                            <option value="">All Status</option>
                            <option value="installed" {% if request.GET.status == 'installed' %}selected{% endif %}>Installed</option>
                            <option value="not_installed" {% if request.GET.status == 'not_installed' %}selected{% endif %}>Not Installed</option>
                            <option value="activated" {% if request.GET.status == 'activated' %}selected{% endif %}>Activated</option>
                            <option value="upgradable" {% if request.GET.status == 'upgradable' %}selected{% endif %}>Upgrade Available</option>
                        </select>
                    </div>
                    <div class="col-md-2">
                        <button type="submit" class="btn btn-primary">Filter</button>
                        <a href="{% url 'plugins:netbox_catalog:catalog_list' %}" class="btn btn-outline-secondary">Clear</a>
                    </div>
                </form>

                <!-- Plugin Grid -->
                <div class="row">
                    {% for plugin in plugins %}
                    <div class="col-md-4 mb-3">
                        <div class="card h-100 {% if plugin.featured %}border-primary{% endif %}">
                            <div class="card-header d-flex justify-content-between align-items-center">
                                <strong>{{ plugin.name }}</strong>
                                {% if plugin.featured %}
                                <span class="badge bg-primary">Featured</span>
                                {% endif %}
                            </div>
                            <div class="card-body">
                                <p class="card-text small">{{ plugin.summary|truncatewords:20 }}</p>
                                <div class="mb-2">
                                    <span class="badge bg-{{ certification_levels|get_item:plugin.certification|get_item:'color'|default:'secondary' }}">
                                        {{ certification_levels|get_item:plugin.certification|get_item:'label'|default:plugin.certification }}
                                    </span>
                                    <span class="badge bg-secondary">{{ plugin.category }}</span>
                                </div>
                                <div class="small text-muted">
                                    <div>v{{ plugin.version }} by {{ plugin.author }}</div>
                                    {% if plugin.installed_version %}
                                    <div class="text-success">
                                        <i class="mdi mdi-check"></i>
                                        Installed: v{{ plugin.installed_version }}
                                        {% if plugin.is_activated %}
                                        (Active)
                                        {% else %}
                                        <span class="text-warning">(Not Activated)</span>
                                        {% endif %}
                                    </div>
                                    {% if plugin.upgrade_available %}
                                    <div class="text-info">
                                        <i class="mdi mdi-arrow-up"></i> Upgrade available
                                    </div>
                                    {% endif %}
                                    {% endif %}
                                </div>
                            </div>
                            <div class="card-footer">
                                <a href="{% url 'plugins:netbox_catalog:plugin_detail' name=plugin.name %}"
                                   class="btn btn-sm btn-outline-primary">Details</a>
                                {% if not plugin.installed_version %}
                                <a href="{% url 'plugins:netbox_catalog:plugin_install' name=plugin.name %}"
                                   class="btn btn-sm btn-success">Install</a>
                                {% elif plugin.upgrade_available %}
                                <a href="{% url 'plugins:netbox_catalog:plugin_install' name=plugin.name %}"
                                   class="btn btn-sm btn-info">Upgrade</a>
                                {% endif %}
                            </div>
                        </div>
                    </div>
                    {% empty %}
                    <div class="col-12">
                        <div class="alert alert-info">No plugins found matching your criteria.</div>
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

#### `plugin_detail.html`

```html
{% extends 'base/layout.html' %}
{% load helpers %}
{% load markdown %}

{% block title %}{{ plugin.name }}{% endblock %}

{% block content %}
<div class="row">
    <div class="col-md-8">
        <div class="card mb-3">
            <div class="card-header">
                <h4>{{ plugin.name }}</h4>
            </div>
            <div class="card-body">
                {% if plugin.description %}
                <div class="plugin-description">
                    {{ plugin.description|render_markdown }}
                </div>
                {% else %}
                <p>{{ plugin.summary }}</p>
                {% endif %}
            </div>
        </div>

        {% if install_logs %}
        <div class="card">
            <div class="card-header">Installation History</div>
            <div class="card-body">
                <table class="table table-sm">
                    <thead>
                        <tr>
                            <th>Action</th>
                            <th>Version</th>
                            <th>Status</th>
                            <th>User</th>
                            <th>Date</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for log in install_logs %}
                        <tr>
                            <td>{{ log.get_action_display }}</td>
                            <td>{{ log.version }}</td>
                            <td>
                                <span class="badge bg-{% if log.status == 'success' %}success{% elif log.status == 'failed' %}danger{% else %}secondary{% endif %}">
                                    {{ log.get_status_display }}
                                </span>
                            </td>
                            <td>{{ log.user }}</td>
                            <td>{{ log.started|date:"Y-m-d H:i" }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        {% endif %}
    </div>

    <div class="col-md-4">
        <div class="card mb-3">
            <div class="card-header">Plugin Info</div>
            <div class="card-body">
                <table class="table table-sm">
                    <tr>
                        <th>Version</th>
                        <td>{{ plugin.version }}</td>
                    </tr>
                    <tr>
                        <th>Author</th>
                        <td>{{ plugin.author }}</td>
                    </tr>
                    <tr>
                        <th>License</th>
                        <td>{{ plugin.license }}</td>
                    </tr>
                    <tr>
                        <th>Category</th>
                        <td>{{ plugin.category }}</td>
                    </tr>
                    <tr>
                        <th>Certification</th>
                        <td>
                            <span class="badge bg-{{ certification_levels|get_item:plugin.certification|get_item:'color'|default:'secondary' }}">
                                {{ certification_levels|get_item:plugin.certification|get_item:'label'|default:plugin.certification }}
                            </span>
                        </td>
                    </tr>
                    <tr>
                        <th>Python</th>
                        <td>{{ plugin.requires_python }}</td>
                    </tr>
                    {% if plugin.netbox_min_version %}
                    <tr>
                        <th>NetBox Min</th>
                        <td>{{ plugin.netbox_min_version }}</td>
                    </tr>
                    {% endif %}
                </table>

                {% if plugin.notes %}
                <div class="alert alert-info">
                    {{ plugin.notes }}
                </div>
                {% endif %}

                {% if plugin.replacement %}
                <div class="alert alert-warning">
                    This plugin is deprecated. Consider using
                    <a href="{% url 'plugins:netbox_catalog:plugin_detail' name=plugin.replacement %}">{{ plugin.replacement }}</a> instead.
                </div>
                {% endif %}
            </div>
        </div>

        <div class="card mb-3">
            <div class="card-header">Status</div>
            <div class="card-body">
                {% if plugin.installed_version %}
                <div class="text-success mb-2">
                    <i class="mdi mdi-check-circle"></i> Installed (v{{ plugin.installed_version }})
                </div>
                {% if plugin.is_activated %}
                <div class="text-success mb-2">
                    <i class="mdi mdi-check-circle"></i> Activated
                </div>
                {% else %}
                <div class="text-warning mb-2">
                    <i class="mdi mdi-alert"></i> Not Activated
                </div>
                {% endif %}
                {% if plugin.upgrade_available %}
                <div class="text-info mb-2">
                    <i class="mdi mdi-arrow-up-circle"></i> Upgrade available (v{{ plugin.version }})
                </div>
                {% endif %}
                {% else %}
                <div class="text-muted mb-2">
                    <i class="mdi mdi-circle-outline"></i> Not Installed
                </div>
                {% endif %}

                <div class="mt-3">
                    {% if not plugin.installed_version %}
                    <a href="{% url 'plugins:netbox_catalog:plugin_install' name=plugin.name %}"
                       class="btn btn-success w-100">Install</a>
                    {% elif plugin.upgrade_available %}
                    <a href="{% url 'plugins:netbox_catalog:plugin_install' name=plugin.name %}"
                       class="btn btn-info w-100">Upgrade to v{{ plugin.version }}</a>
                    {% endif %}
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">Links</div>
            <div class="card-body">
                {% if plugin.home_page %}
                <a href="{{ plugin.home_page }}" target="_blank" class="btn btn-outline-secondary btn-sm w-100 mb-2">
                    <i class="mdi mdi-home"></i> Homepage
                </a>
                {% endif %}
                {% for name, url in plugin.project_urls.items %}
                <a href="{{ url }}" target="_blank" class="btn btn-outline-secondary btn-sm w-100 mb-2">
                    <i class="mdi mdi-link"></i> {{ name }}
                </a>
                {% endfor %}
                <a href="https://pypi.org/project/{{ plugin.name }}/" target="_blank"
                   class="btn btn-outline-secondary btn-sm w-100">
                    <i class="mdi mdi-package"></i> PyPI
                </a>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

#### `plugin_install.html`

```html
{% extends 'base/layout.html' %}

{% block title %}Install {{ plugin.name }}{% endblock %}

{% block content %}
<div class="row">
    <div class="col-md-8 offset-md-2">
        <div class="card">
            <div class="card-header">
                <h4>Install {{ plugin.name }}</h4>
            </div>
            <div class="card-body">
                {% if error %}
                <div class="alert alert-danger">
                    <strong>Installation Failed:</strong>
                    <pre>{{ error }}</pre>
                </div>
                {% if output %}
                <div class="alert alert-secondary">
                    <strong>Output:</strong>
                    <pre>{{ output }}</pre>
                </div>
                {% endif %}
                {% endif %}

                <div class="alert alert-info">
                    <h5>Before Installing</h5>
                    <p>After pip installation completes, you will need to:</p>
                    <ol>
                        <li>Add the plugin to <code>PLUGINS</code> in <code>configuration.py</code></li>
                        <li>Run database migrations</li>
                        <li>Collect static files</li>
                        <li><strong>Restart NetBox</strong></li>
                    </ol>
                </div>

                <form method="post">
                    {% csrf_token %}

                    <div class="mb-3">
                        <label class="form-label">Package</label>
                        <input type="text" class="form-control" value="{{ plugin.name }}" disabled>
                    </div>

                    <div class="mb-3">
                        <label class="form-label">Version</label>
                        <input type="text" name="version" class="form-control"
                               value="{{ form.version.value|default:plugin.version }}"
                               placeholder="Latest: {{ plugin.version }}">
                        <div class="form-text">Leave empty to install the latest version.</div>
                    </div>

                    <div class="mb-3">
                        <label class="form-label">Configuration Snippet</label>
                        <pre class="bg-dark text-light p-3"><code>{{ config_snippet }}</code></pre>
                        <div class="form-text">You will need to add this to your configuration.py</div>
                    </div>

                    <div class="mb-3 form-check">
                        <input type="checkbox" name="confirm" class="form-check-input" id="confirm" required>
                        <label class="form-check-label" for="confirm">
                            I understand that I need to edit configuration.py and restart NetBox after installation
                        </label>
                    </div>

                    <div class="d-flex justify-content-between">
                        <a href="{% url 'plugins:netbox_catalog:plugin_detail' name=plugin.name %}"
                           class="btn btn-outline-secondary">Cancel</a>
                        <button type="submit" class="btn btn-success">
                            {% if plugin.installed_version %}Upgrade{% else %}Install{% endif %} {{ plugin.name }}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

#### `plugin_installed.html`

```html
{% extends 'base/layout.html' %}

{% block title %}{{ plugin.name }} Installed{% endblock %}

{% block content %}
<div class="row">
    <div class="col-md-8 offset-md-2">
        <div class="card">
            <div class="card-header bg-success text-white">
                <h4><i class="mdi mdi-check-circle"></i> Successfully Installed {{ plugin.name }}</h4>
            </div>
            <div class="card-body">
                <div class="alert alert-warning">
                    <h5><i class="mdi mdi-alert"></i> Action Required</h5>
                    <p>The package has been installed, but you need to complete these steps:</p>
                </div>

                <h5>Step 1: Edit configuration.py</h5>
                <p>Add the following to your NetBox configuration file:</p>
                <pre class="bg-dark text-light p-3"><code>{{ config_snippet }}</code></pre>

                <h5>Step 2: Run Migrations</h5>
                <p>Execute the following command:</p>
                <pre class="bg-dark text-light p-3"><code>{{ migrate_command }}</code></pre>

                <h5>Step 3: Collect Static Files</h5>
                <p>Execute the following command:</p>
                <pre class="bg-dark text-light p-3"><code>{{ collectstatic_command }}</code></pre>

                <h5>Step 4: Restart NetBox</h5>
                <p>Restart your NetBox service/container to load the plugin.</p>
                <pre class="bg-dark text-light p-3"><code># Docker Compose
docker-compose restart netbox

# Systemd
sudo systemctl restart netbox</code></pre>

                <div class="mt-4 d-flex justify-content-between">
                    <a href="{% url 'plugins:netbox_catalog:catalog_list' %}" class="btn btn-outline-secondary">
                        Back to Catalog
                    </a>
                    <a href="{% url 'plugins:netbox_catalog:plugin_detail' name=plugin.name %}" class="btn btn-primary">
                        View Plugin Details
                    </a>
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}
```

## Files to Create

| File | Purpose | Lines (est.) |
|------|---------|--------------|
| `pyproject.toml` | Package metadata, dependencies | 55 |
| `catalog.json` | Curated plugin data | 100+ |
| `netbox_catalog/__init__.py` | Plugin config | 35 |
| `netbox_catalog/pypi_client.py` | PyPI API client | 130 |
| `netbox_catalog/catalog_service.py` | Merge PyPI + curated data | 180 |
| `netbox_catalog/installer.py` | pip install wrapper | 120 |
| `netbox_catalog/compatibility.py` | Version compatibility checker | 150 |
| `netbox_catalog/models.py` | InstallationLog model | 45 |
| `netbox_catalog/views.py` | Catalog views | 200 |
| `netbox_catalog/tables.py` | Django tables | 25 |
| `netbox_catalog/filtersets.py` | Filter sets | 30 |
| `netbox_catalog/forms.py` | Forms | 50 |
| `netbox_catalog/urls.py` | URL routing | 15 |
| `netbox_catalog/navigation.py` | Plugin menu | 25 |
| `netbox_catalog/api/` | API endpoints | 100 |
| `templates/catalog_list.html` | Plugin browser | 120 |
| `templates/plugin_detail.html` | Plugin details | 150 |
| `templates/plugin_install.html` | Install form | 80 |
| `templates/plugin_installed.html` | Post-install | 70 |
| `README.md` | Documentation | 150 |

**Total estimated: ~1,830 lines**

## API Endpoints Used

### PyPI API

1. **List All Packages** (filtered locally)
   ```
   GET https://pypi.org/simple/
   Accept: application/vnd.pypi.simple.v1+json
   ```

2. **Get Package Details**
   ```
   GET https://pypi.org/pypi/{package_name}/json
   ```

## Configuration Example

```python
PLUGINS = [
    'netbox_catalog',
]

PLUGINS_CONFIG = {
    'netbox_catalog': {
        'pypi_cache_timeout': 3600,           # Cache PyPI data for 1 hour
        'catalog_json_url': '',               # Optional: remote catalog.json URL
        'allow_install': True,                # Enable pip install feature
        'show_uncurated': True,               # Show all netbox-* packages
        'pypi_index_url': 'https://pypi.org', # PyPI mirror support
    }
}
```

## NetBox Version Compatibility Detection

### The Challenge

NetBox plugins declare compatibility via `min_version` and `max_version` in their `PluginConfig` class, but this information is only accessible **after** the package is installed (it's inside the Python code). PyPI metadata doesn't include NetBox-specific version constraints.

### Detection Strategy (Multi-Layered)

| Priority | Source | When Available | Reliability |
|----------|--------|----------------|-------------|
| 1 | Curated catalog JSON | Always | High (manual) |
| 2 | PluginConfig import | After pip install | High (authoritative) |
| 3 | README parsing | Before install | Low (regex) |
| 4 | PyPI requires_dist | Before install | Very low (rarely used) |

### Implementation

#### 1. Primary: Curated JSON (Pre-Install)

The `catalog.json` file contains manually verified compatibility:

```json
{
    "plugins": {
        "netbox-bgp": {
            "netbox_min_version": "4.0.0",
            "netbox_max_version": null,
            "netbox_tested_versions": ["4.3", "4.4", "4.5"]
        }
    }
}
```

#### 2. Secondary: Import PluginConfig (Post-Install)

After `pip install` completes (but before activation), we can import the module and read version constraints:

```python
# compatibility_checker.py

import importlib
import sys
from typing import Optional
from packaging.version import Version

from django.conf import settings


class CompatibilityChecker:
    """Check plugin compatibility with current NetBox version."""

    def __init__(self):
        self.netbox_version = Version(settings.VERSION)

    def get_plugin_constraints(self, package_name: str) -> dict:
        """
        Import an installed plugin and read its version constraints.

        This works AFTER pip install but BEFORE adding to PLUGINS list.
        """
        module_name = package_name.replace("-", "_")

        try:
            # Import the plugin module
            module = importlib.import_module(module_name)

            # Get the PluginConfig class (conventionally named 'config')
            config_class = getattr(module, 'config', None)

            if config_class is None:
                # Try to find it in the module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and
                        hasattr(attr, 'min_version') and
                        hasattr(attr, 'name')):
                        config_class = attr
                        break

            if config_class:
                return {
                    "min_version": getattr(config_class, 'min_version', None),
                    "max_version": getattr(config_class, 'max_version', None),
                    "name": getattr(config_class, 'name', module_name),
                    "version": getattr(config_class, 'version', None),
                }
        except ImportError as e:
            # Plugin not installed or import failed
            pass
        except Exception as e:
            # Other errors during import
            pass

        return {}

    def check_compatibility(self, package_name: str,
                           min_version: str = None,
                           max_version: str = None) -> dict:
        """
        Check if a plugin is compatible with current NetBox version.

        Returns dict with:
        - compatible: bool
        - reason: str (if not compatible)
        - min_version: str
        - max_version: str
        """
        result = {
            "compatible": True,
            "reason": None,
            "min_version": min_version,
            "max_version": max_version,
            "current_netbox_version": str(self.netbox_version),
        }

        if min_version:
            if self.netbox_version < Version(min_version):
                result["compatible"] = False
                result["reason"] = f"Requires NetBox >= {min_version}"
                return result

        if max_version:
            if self.netbox_version > Version(max_version):
                result["compatible"] = False
                result["reason"] = f"Requires NetBox <= {max_version}"
                return result

        return result

    def get_full_compatibility_info(self, package_name: str,
                                    curated_data: dict = None) -> dict:
        """
        Get full compatibility info from all sources.

        Priority:
        1. Curated catalog data
        2. Installed plugin's PluginConfig
        3. Unknown
        """
        min_version = None
        max_version = None
        source = "unknown"

        # Check curated data first
        if curated_data:
            min_version = curated_data.get("netbox_min_version")
            max_version = curated_data.get("netbox_max_version")
            if min_version or max_version:
                source = "curated"

        # If no curated data, try importing the plugin (if installed)
        if not min_version and not max_version:
            constraints = self.get_plugin_constraints(package_name)
            if constraints:
                min_version = constraints.get("min_version")
                max_version = constraints.get("max_version")
                if min_version or max_version:
                    source = "plugin_config"

        # Check compatibility
        compat_result = self.check_compatibility(
            package_name, min_version, max_version
        )
        compat_result["source"] = source

        return compat_result
```

#### 3. Fallback: README Parsing (Best Effort)

Some plugins include compatibility tables in their README. We can attempt to parse these:

```python
import re
from typing import Optional

def parse_netbox_version_from_readme(description: str) -> Optional[str]:
    """
    Attempt to extract NetBox version from README text.

    Looks for patterns like:
    - "NetBox 4.x"
    - "NetBox >= 4.0"
    - "Requires NetBox 4.0+"
    - Markdown tables with version info
    """
    if not description:
        return None

    patterns = [
        # "NetBox 4.x" or "NetBox 4.5.x"
        r'NetBox\s+(\d+\.\d+)(?:\.x)?',
        # "NetBox >= 4.0" or "NetBox >=4.0"
        r'NetBox\s*>=?\s*(\d+\.\d+)',
        # "requires NetBox 4.0" (case insensitive)
        r'[Rr]equires\s+NetBox\s+(\d+\.\d+)',
        # Version table: "| 4.5.x | 1.0.0 |"
        r'\|\s*(\d+\.\d+)\.x\s*\|',
    ]

    for pattern in patterns:
        match = re.search(pattern, description)
        if match:
            return match.group(1)

    return None
```

### UI Display

The catalog will show compatibility status with clear indicators:

```
┌─────────────────────────────────────────────┐
│  netbox-bgp                     v0.18.0     │
├─────────────────────────────────────────────┤
│  ✅ Compatible with NetBox 4.5              │
│     Requires: 4.0.0 - latest                │
│     Source: curated catalog                 │
├─────────────────────────────────────────────┤
│  [Install]                                  │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  netbox-old-plugin              v1.0.0      │
├─────────────────────────────────────────────┤
│  ⚠️ Compatibility Unknown                   │
│     No version constraints found            │
│     Source: unknown                         │
├─────────────────────────────────────────────┤
│  [Install at your own risk]                 │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  netbox-legacy                  v2.0.0      │
├─────────────────────────────────────────────┤
│  ❌ Incompatible                            │
│     Requires NetBox <= 3.7                  │
│     Your version: 4.5.0                     │
├─────────────────────────────────────────────┤
│  [Not Available]                            │
└─────────────────────────────────────────────┘
```

### Post-Install Verification

After pip install, we verify compatibility before showing config instructions:

```python
def verify_after_install(self, package_name: str) -> dict:
    """
    After pip install, import the plugin and verify compatibility.

    This catches cases where curated data was wrong or missing.
    """
    constraints = self.get_plugin_constraints(package_name)

    if constraints:
        compat = self.check_compatibility(
            package_name,
            constraints.get("min_version"),
            constraints.get("max_version")
        )

        if not compat["compatible"]:
            return {
                "status": "warning",
                "message": f"Plugin installed but may not be compatible: {compat['reason']}",
                "constraints": constraints,
            }

    return {
        "status": "ok",
        "message": "Plugin installed successfully",
        "constraints": constraints,
    }
```

## Security Considerations

1. **pip install in container** - Only admins with proper permissions should be able to install
2. **Package verification** - Consider adding checksum verification in future
3. **Curated list** - The curated JSON can mark suspicious packages as "not recommended"
4. **Rate limiting** - PyPI requests are cached to avoid rate limits
5. **Network access** - Plugin needs outbound HTTPS access to pypi.org

## Future Enhancements

1. **Remote catalog.json** - Host curated catalog externally for updates without plugin release
2. **Dependency resolution** - Show what other packages will be installed
3. **Rollback support** - Track previous versions for rollback
4. **Auto-update** - Scheduled checks for new versions
5. **Compatibility matrix** - Test against multiple NetBox versions
6. **User ratings/reviews** - Community feedback on plugins
7. **Plugin health checks** - Verify plugin loads correctly after install
8. **Bulk operations** - Install/update multiple plugins at once
9. **Requirements.txt export** - Export installed plugins for reproducibility
10. **Webhook notifications** - Notify when new versions are available
