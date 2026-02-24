import importlib
import logging
import re

from django.conf import settings
from packaging.version import InvalidVersion, Version

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
    match = re.match(r"^(\d+\.\d+\.\d+)", version_string)
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
            config_class = getattr(module, "config", None)

            if config_class is None:
                # Try to find it in the module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and hasattr(attr, "min_version")
                        and hasattr(attr, "name")
                    ):
                        config_class = attr
                        break

            if config_class:
                return {
                    "min_version": getattr(config_class, "min_version", None),
                    "max_version": getattr(config_class, "max_version", None),
                    "name": getattr(config_class, "name", module_name),
                    "version": getattr(config_class, "version", None),
                }
        except ImportError:
            # Plugin not installed or import failed
            pass
        except Exception as e:
            logger.warning(f"Error reading plugin constraints for {package_name}: {e}")

        return {}

    def check_compatibility(
        self, package_name: str, min_version: str = None, max_version: str = None
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
        curated_data: dict = None,
        pypi_info: dict = None,
    ) -> dict:
        """
        Get full compatibility info from all sources.

        Priority:
        1. Curated catalog data
        2. Installed plugin's PluginConfig
        3. README/description parsing
        4. Unknown
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

        # If still nothing, try parsing the README/description
        if not min_version and not max_version and pypi_info:
            readme_constraints = parse_netbox_version_from_readme(
                pypi_info.get("description", ""),
                pypi_info.get("version", ""),
            )
            if readme_constraints:
                min_version = readme_constraints.get("min_version")
                max_version = readme_constraints.get("max_version")
                if min_version or max_version:
                    source = "readme"

        # Check compatibility
        compat_result = self.check_compatibility(package_name, min_version, max_version)
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
                constraints.get("max_version"),
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


def parse_netbox_version_from_readme(
    description: str, plugin_version: str = ""
) -> dict:
    """
    Extract NetBox version constraints from README text.

    Handles:
    - Version compatibility tables (markdown)
    - Inline patterns like "NetBox >= 4.0", "Requires NetBox 4.0+"
    - "NetBox 4.x" or "NetBox 4.5.x" mentions

    If plugin_version is provided, tries to match the specific row in a
    compatibility table. Otherwise returns the last (most recent) row.

    Returns dict with 'min_version' and optionally 'max_version', or empty dict.
    """
    if not description:
        return {}

    # Step 1: Check for shields.io badge (highest trust - explicitly set by author)
    badge_patterns = [
        r"(?:badge|img\.shields\.io/badge)[/]NetBox[-%](\d+\.\d+)",
        r"!\[.*?NetBox[- ]+(\d+\.\d+)\+?.*?\]",
    ]
    for pattern in badge_patterns:
        match = re.search(pattern, description)
        if match:
            return {"min_version": match.group(1)}

    # Step 2: Try to parse a version compatibility table
    table_result = _parse_version_table(description, plugin_version)
    if table_result:
        return table_result

    # Step 3: Fall back to inline text patterns
    inline_patterns = [
        r"NetBox\s*>=\s*(\d+\.\d+(?:\.\d+)?)",
        r"[Rr]equires\s+NetBox\s+(\d+\.\d+(?:\.\d+)?)\+?",
        r"NetBox\s+(\d+\.\d+)(?:\.x)?",
    ]

    for pattern in inline_patterns:
        match = re.search(pattern, description)
        if match:
            return {"min_version": match.group(1)}

    return {}


def _parse_version_table(description: str, plugin_version: str = "") -> dict:
    """
    Parse a markdown version compatibility table from README.

    Handles two common formats:
    Format A: | Plugin Version | NetBox version |  (ipcalculator style)
    Format B: | NetBox Version | Plugin Version |  (netbox-bgp style)

    Detects column order from header row and extracts NetBox constraints.
    """
    lines = description.split("\n")
    header_line = None
    table_rows = []
    in_table = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            # Separator row
            if re.match(r"^\|[\s\-:]+\|[\s\-:]+\|", stripped):
                in_table = True
                continue
            if not in_table:
                header_line = stripped  # Save header (before separator)
                continue
            table_rows.append(stripped)
        else:
            if in_table and table_rows:
                break

    if not table_rows:
        return {}

    # Detect column order from header
    # Default: col0=plugin version, col1=netbox version
    netbox_col = 1
    plugin_col = 0
    if header_line:
        headers = [h.strip().lower() for h in header_line.split("|") if h.strip()]
        for i, h in enumerate(headers):
            if "netbox" in h:
                netbox_col = i
                plugin_col = 1 - i if len(headers) == 2 else (0 if i != 0 else 1)
                break

    # Detect table order (ascending vs descending) to choose matching strategy
    is_ascending = _detect_table_order(table_rows, plugin_col)

    first_matched = {}
    last_matched = {}
    first_constraints = {}
    last_constraints = {}
    for row in table_rows:
        cells = [c.strip() for c in row.split("|") if c.strip()]
        if len(cells) < 2:
            continue

        netbox_cell = cells[netbox_col] if netbox_col < len(cells) else ""
        plugin_cell = cells[plugin_col] if plugin_col < len(cells) else ""

        # Parse the NetBox version cell
        constraints = _parse_version_cell(netbox_cell)

        # If no >= or <= found, try "NetBox X.Y.x" or just "X.Y.x" as min_version
        if not constraints:
            ver_match = re.search(r"(\d+\.\d+)(?:\.[xX])?", netbox_cell)
            if ver_match:
                constraints = {"min_version": ver_match.group(1)}

        if not constraints:
            continue

        # Track first and last constraints for fallback
        if not first_constraints:
            first_constraints = constraints
        last_constraints = constraints

        # Match against plugin version (only use >= heuristic for ascending tables)
        if plugin_version and _version_matches_row(
            plugin_version, plugin_cell, allow_gte=is_ascending
        ):
            if not first_matched:
                first_matched = constraints
            last_matched = constraints

    # Ascending: last match wins (later rows are more specific overrides)
    #   Fallback: last row (newest entry)
    # Descending: first match wins (first row is the most relevant)
    #   Fallback: first row (newest entry)
    if is_ascending:
        return last_matched or last_constraints
    else:
        return first_matched or first_constraints


def _detect_table_order(table_rows: list, plugin_col: int) -> bool:
    """Detect if table is in ascending order (True) or descending (False)."""
    versions = []
    for row in table_rows:
        cells = [c.strip() for c in row.split("|") if c.strip()]
        if len(cells) > plugin_col:
            cell = re.sub(r"^[=<>!\s]+", "", cells[plugin_col].strip()).lstrip("v")
            # Extract version number
            ver_match = re.match(r"(\d+\.\d+(?:\.\d+)?)", cell)
            if ver_match:
                try:
                    versions.append(Version(ver_match.group(1)))
                except InvalidVersion:
                    pass
    if len(versions) >= 2:
        return versions[0] < versions[-1]  # First < Last = ascending
    return True  # Default to ascending


def _parse_version_cell(cell: str) -> dict:
    """
    Parse a version constraint cell like '>=4.3', '>=3.7 and <=4.2', '<=3.7'.

    Returns dict with 'min_version' and/or 'max_version'.
    """
    result = {}

    # Match >=X.Y or >=X.Y.Z
    min_match = re.search(r">=?\s*(\d+\.\d+(?:\.\d+)?)", cell)
    if min_match:
        result["min_version"] = min_match.group(1)

    # Match <=X.Y or <=X.Y.Z
    max_match = re.search(r"<=?\s*(\d+\.\d+(?:\.\d+)?)", cell)
    if max_match:
        result["max_version"] = max_match.group(1)

    return result


def _version_matches_row(
    plugin_version: str, row_version_text: str, allow_gte: bool = True
) -> bool:
    """
    Check if a plugin version matches a row's version specifier.

    Handles patterns like 'v1.4.10', 'v1.4.x', 'v0.0-1.3', '= v4.5.0'.
    If allow_gte is False or the row has an '=' prefix, specific versions
    are matched exactly only (no >= heuristic).
    """
    raw = row_version_text.strip()
    is_exact = raw.startswith("=") and not raw.startswith(">=")

    # Clean up: strip '=', '>=', 'v' prefixes
    pv = plugin_version.lstrip("v")
    rv = re.sub(r"^[=<>!\s]+", "", raw).lstrip("v")

    # Exact match
    if pv == rv:
        return True

    # Wildcard match: "1.4.x" or "4.5.X" matches "1.4.10" or "4.5.0"
    if rv.lower().endswith(".x"):
        prefix = rv[:-1]  # "1.4." or "4.5."
        if pv.startswith(prefix):
            return True

    # Range match: "0.0-1.3" - check if plugin version is in range
    range_match = re.match(r"(\d+\.\d+(?:\.\d+)?)\s*-\s*(\d+\.\d+(?:\.\d+)?)", rv)
    if range_match:
        try:
            low = Version(range_match.group(1))
            high = Version(range_match.group(2))
            ver = Version(pv)
            return low <= ver <= high
        except InvalidVersion:
            pass

    # Specific version without '=' prefix: "1.4.10" matches >= 1.4.10
    # Only enabled for ascending tables where later rows override earlier
    if allow_gte and not is_exact:
        try:
            row_ver = Version(rv)
            plugin_ver = Version(pv)
            return plugin_ver >= row_ver
        except InvalidVersion:
            pass

    return False
