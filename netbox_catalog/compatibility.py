import importlib
import re
import logging
from typing import Optional

from packaging.version import Version, InvalidVersion

from django.conf import settings

logger = logging.getLogger(__name__)


def parse_netbox_version(version_string: str) -> Version:
    """
    Parse NetBox version string, handling Docker-specific suffixes.

    NetBox Docker images use versions like '4.5.1-Docker-3.4.2'.
    We need to extract just the NetBox version (4.5.1).
    """
    if not version_string:
        return Version("0.0.0")

    # Try parsing as-is first
    try:
        return Version(version_string)
    except InvalidVersion:
        pass

    # Extract version number from string like '4.5.1-Docker-3.4.2'
    match = re.match(r'^(\d+\.\d+\.\d+)', version_string)
    if match:
        try:
            return Version(match.group(1))
        except InvalidVersion:
            pass

    # Fallback
    logger.warning(f"Could not parse NetBox version: {version_string}")
    return Version("0.0.0")


class CompatibilityChecker:
    """Check plugin compatibility with current NetBox version."""

    def __init__(self):
        self.netbox_version = parse_netbox_version(settings.VERSION)

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
        except ImportError:
            # Plugin not installed or import failed
            pass
        except Exception as e:
            logger.warning(f"Error reading plugin constraints for {package_name}: {e}")

        return {}

    def check_compatibility(
        self,
        package_name: str,
        min_version: str = None,
        max_version: str = None
    ) -> dict:
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
            try:
                if self.netbox_version < Version(min_version):
                    result["compatible"] = False
                    result["reason"] = f"Requires NetBox >= {min_version}"
                    return result
            except Exception:
                pass

        if max_version:
            try:
                if self.netbox_version > Version(max_version):
                    result["compatible"] = False
                    result["reason"] = f"Requires NetBox <= {max_version}"
                    return result
            except Exception:
                pass

        return result

    def get_full_compatibility_info(
        self,
        package_name: str,
        curated_data: dict = None
    ) -> dict:
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


def parse_netbox_version_from_readme(description: str) -> Optional[str]:
    """
    Attempt to extract NetBox version from README text.

    Looks for patterns like:
    - "NetBox 4.x" or "NetBox 4.5.x"
    - "NetBox >= 4.0" or "NetBox >=4.0"
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
