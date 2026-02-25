import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
from django.conf import settings
from django.core.cache import cache

from .compatibility import CompatibilityChecker
from .pypi_client import PyPIClient

logger = logging.getLogger(__name__)


@dataclass
class PluginInfo:
    """Combined plugin information from PyPI and curated catalog."""

    name: str
    version: str
    summary: str = ""
    description: str = ""
    description_content_type: str = ""
    author: str = ""
    license: str = ""
    keywords: list = field(default_factory=list)
    home_page: str = ""
    project_urls: dict = field(default_factory=dict)
    requires_python: str = ""
    requires_dist: list = field(default_factory=list)
    releases: list = field(default_factory=list)
    last_updated: str = ""

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

    # Download stats (from pypistats.org)
    downloads_last_day: int = 0
    downloads_last_week: int = 0
    downloads_last_month: int = 0

    # Runtime status
    installed_version: str = ""
    is_activated: bool = False
    upgrade_available: bool = False

    # Compatibility status (computed)
    is_compatible: bool = True
    compatibility_reason: str = ""
    compatibility_source: str = "unknown"

    @property
    def module_name(self) -> str:
        """Get the Python module name (hyphens to underscores)."""
        return self.name.replace("-", "_")

    @property
    def downloads_display(self) -> str:
        """Format monthly downloads for display (e.g., '1.2K', '15K')."""
        count = self.downloads_last_month
        if count >= 1_000_000:
            return f"{count / 1_000_000:.1f}M"
        if count >= 1_000:
            return f"{count / 1_000:.1f}K"
        return str(count)


class CatalogService:
    """Service for managing the plugin catalog."""

    def __init__(self):
        self.pypi_client = PyPIClient()
        self.compatibility_checker = CompatibilityChecker()
        self._curated_data = None
        self._installed_packages = None

    @property
    def curated_data(self) -> dict:
        """Load curated catalog data."""
        if self._curated_data is None:
            self._curated_data = self._load_curated_catalog()
        return self._curated_data

    def _load_curated_catalog(self) -> dict:
        """Load curated catalog from file or URL."""
        # Try remote URL first
        config = getattr(settings, "PLUGINS_CONFIG", {}).get("netbox_catalog", {})
        remote_url = config.get("catalog_json_url")

        if remote_url:
            try:
                response = requests.get(remote_url, timeout=30)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                logger.warning(f"Failed to fetch remote catalog: {e}")

        # Fall back to local file
        catalog_path = Path(__file__).parent / "catalog.json"
        if catalog_path.exists():
            try:
                with open(catalog_path) as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse catalog.json: {e}")

        return {"plugins": {}, "categories": [], "certification_levels": {}}

    def get_all_plugins(self, include_uncurated: bool = True) -> list[PluginInfo]:
        """Get all available plugins with merged metadata.

        Download stats come from catalog.json (updated weekly by GitHub Action)
        to avoid slow pypistats.org API calls on every page load.
        """
        plugins = []

        # Get all netbox packages from PyPI
        package_names = self.pypi_client.get_all_netbox_packages()

        # Filter package names before fetching details
        if not include_uncurated:
            curated_plugins = self.curated_data.get("plugins", {})
            package_names = [n for n in package_names if n in curated_plugins]

        # Get installed packages
        installed = self._get_installed_packages()
        activated = self._get_activated_plugins()

        # Fetch PyPI info in parallel (no pypistats - those come from catalog.json)
        pypi_data = {}
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {
                executor.submit(self.pypi_client.get_package_info, name): name
                for name in package_names
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    result = future.result()
                    if result:
                        pypi_data[name] = result
                except Exception as e:
                    logger.debug(f"Error fetching {name}: {e}")

        # Build plugin list (preserving original order)
        for name in package_names:
            if name not in pypi_data:
                continue

            pypi_info = pypi_data[name]
            curated_info = self.curated_data.get("plugins", {}).get(name, {})

            # Merge into PluginInfo (includes download stats from catalog.json)
            plugin = self._merge_plugin_info(name, pypi_info, curated_info)

            # Add runtime status
            if name in installed:
                plugin.installed_version = installed[name]
                plugin.upgrade_available = plugin.version != installed[name]

            # Check module name variations for activation
            module_name = name.replace("-", "_")
            plugin.is_activated = module_name in activated

            # Check compatibility (pass pypi_info for README fallback parsing)
            compat_info = self.compatibility_checker.get_full_compatibility_info(
                name, curated_info, pypi_info=pypi_info
            )
            plugin.is_compatible = compat_info.get("compatible", True)
            plugin.compatibility_reason = compat_info.get("reason", "")
            plugin.compatibility_source = compat_info.get("source", "unknown")

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

        # Check compatibility (pass pypi_info for README fallback parsing)
        compat_info = self.compatibility_checker.get_full_compatibility_info(
            name, curated_info, pypi_info=pypi_info
        )
        plugin.is_compatible = compat_info.get("compatible", True)
        plugin.compatibility_reason = compat_info.get("reason", "")
        plugin.compatibility_source = compat_info.get("source", "unknown")

        # Fetch download stats
        stats = self.pypi_client.get_download_stats(name)
        if stats:
            plugin.downloads_last_day = stats.get("last_day", 0)
            plugin.downloads_last_week = stats.get("last_week", 0)
            plugin.downloads_last_month = stats.get("last_month", 0)

        return plugin

    def _merge_plugin_info(
        self, name: str, pypi_info: dict, curated_info: dict
    ) -> PluginInfo:
        """Merge PyPI and curated data into PluginInfo."""
        keywords = pypi_info.get("keywords") or ""
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]

        # Download stats from catalog.json (updated weekly by GitHub Action)
        downloads = curated_info.get("downloads", {})

        return PluginInfo(
            name=name,
            version=pypi_info.get("version", ""),
            summary=pypi_info.get("summary", ""),
            description=pypi_info.get("description", ""),
            description_content_type=pypi_info.get("description_content_type", ""),
            author=pypi_info.get("author", ""),
            license=pypi_info.get("license", ""),
            keywords=keywords,
            home_page=pypi_info.get("home_page", ""),
            project_urls=pypi_info.get("project_urls", {}),
            requires_python=pypi_info.get("requires_python", ""),
            requires_dist=pypi_info.get("requires_dist") or [],
            releases=pypi_info.get("releases", []),
            last_updated=pypi_info.get("last_updated", ""),
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
            # Download stats from catalog.json
            downloads_last_day=downloads.get("last_day", 0),
            downloads_last_week=downloads.get("last_week", 0),
            downloads_last_month=downloads.get("last_month", 0),
        )

    def _get_installed_packages(self) -> dict[str, str]:
        """Get dict of installed package names to versions."""
        if self._installed_packages is not None:
            return self._installed_packages

        cache_key = "netbox_catalog:installed_packages"
        cached = cache.get(cache_key)
        if cached:
            self._installed_packages = cached
            return cached

        try:
            import subprocess
            import sys

            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--format=json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                packages = json.loads(result.stdout)
                installed = {p["name"]: p["version"] for p in packages}
                cache.set(cache_key, installed, 60)  # Cache for 1 minute
                self._installed_packages = installed
                return installed
        except Exception as e:
            logger.error(f"Failed to get installed packages: {e}")

        self._installed_packages = {}
        return {}

    def _get_activated_plugins(self) -> list[str]:
        """Get list of activated plugin module names."""
        return list(getattr(settings, "PLUGINS", []))

    def get_categories(self) -> list[str]:
        """Get list of available categories."""
        return self.curated_data.get("categories", [])

    def get_certification_levels(self) -> dict:
        """Get certification level definitions."""
        return self.curated_data.get("certification_levels", {})

    def refresh_cache(self):
        """Clear cached data to force refresh."""
        self.pypi_client.clear_cache()
        cache.delete("netbox_catalog:installed_packages")
        self._curated_data = None
        self._installed_packages = None
