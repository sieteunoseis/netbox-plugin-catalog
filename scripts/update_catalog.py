#!/usr/bin/env python3
"""
Scan PyPI for netbox-* packages and update catalog.json.

- Fetches download stats from pypistats.org for ALL curated plugins
- Auto-adds newly discovered popular plugins (>100 monthly downloads)
- Stores download stats in catalog.json so the browse page doesn't need
  to hit pypistats.org on every page load

Run weekly via GitHub Actions or manually.
"""

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import requests

PYPI_SIMPLE_URL = "https://pypi.org/simple/"
PYPI_JSON_URL = "https://pypi.org/pypi/{package}/json"
PYPISTATS_URL = "https://pypistats.org/api/packages/{package}/recent"
CATALOG_PATH = Path(__file__).parent.parent / "netbox_catalog" / "catalog.json"
NETBOX_PREFIXES = ["netbox-", "netbox_"]
MIN_DOWNLOADS_FOR_AUTO_ADD = 100  # Monthly downloads threshold


def get_all_netbox_packages():
    """Fetch all netbox-* package names from PyPI."""
    print("Fetching package list from PyPI...")
    resp = requests.get(
        PYPI_SIMPLE_URL,
        headers={"Accept": "application/vnd.pypi.simple.v1+json"},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    packages = [
        p["name"]
        for p in data.get("projects", [])
        if any(p["name"].lower().startswith(prefix) for prefix in NETBOX_PREFIXES)
    ]
    print(f"Found {len(packages)} netbox-* packages on PyPI")
    return packages


def get_download_stats(package_name):
    """Fetch download stats from pypistats.org."""
    try:
        resp = requests.get(
            PYPISTATS_URL.format(package=package_name),
            headers={"Accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("data", {})
    except requests.RequestException:
        return {}


def get_package_info(package_name):
    """Fetch package metadata from PyPI JSON API."""
    try:
        resp = requests.get(
            PYPI_JSON_URL.format(package=package_name),
            headers={"Accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("info", {})
    except requests.RequestException:
        return {}


def fetch_stats_batch(package_names):
    """Fetch download stats sequentially with rate limiting.

    pypistats.org has rate limits, so we add a delay between requests.
    """
    results = {}
    for i, name in enumerate(package_names):
        stats = get_download_stats(name)
        if stats:
            results[name] = stats
        # Rate limit: ~5 requests per second
        if (i + 1) % 5 == 0:
            time.sleep(1)
    return results


def parse_netbox_version_from_readme(description, plugin_version=""):
    """Extract NetBox version constraints from README text."""
    if not description:
        return {}

    # Try version compatibility table first
    lines = description.split("\n")
    table_rows = []
    in_table = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            if re.match(r"^\|[\s\-:]+\|[\s\-:]+\|", stripped):
                in_table = True
                continue
            if not in_table:
                continue
            table_rows.append(stripped)
        else:
            if in_table and table_rows:
                break

    if table_rows:
        best = {}
        for row in table_rows:
            cells = [c.strip() for c in row.split("|") if c.strip()]
            if len(cells) < 2:
                continue
            row_netbox_ver = cells[1]
            constraints = {}
            min_m = re.search(r">=?\s*(\d+\.\d+(?:\.\d+)?)", row_netbox_ver)
            if min_m:
                constraints["min_version"] = min_m.group(1)
            max_m = re.search(r"<=?\s*(\d+\.\d+(?:\.\d+)?)", row_netbox_ver)
            if max_m:
                constraints["max_version"] = max_m.group(1)
            if constraints:
                # Check if this row matches plugin version
                if plugin_version:
                    rv = cells[0].strip().lstrip("v")
                    pv = plugin_version.lstrip("v")
                    if pv == rv or (rv.endswith(".x") and pv.startswith(rv[:-1])):
                        return constraints
                best = constraints
        if best:
            return best

    # Inline patterns fallback
    for pattern in [
        r"NetBox\s*>=\s*(\d+\.\d+(?:\.\d+)?)",
        r"[Rr]equires\s+NetBox\s+(\d+\.\d+(?:\.\d+)?)\+?",
        r"NetBox\s+(\d+\.\d+)(?:\.x)?",
    ]:
        match = re.search(pattern, description)
        if match:
            return {"min_version": match.group(1)}

    return {}


def update_catalog():
    """Main update logic."""
    # Load existing catalog
    with open(CATALOG_PATH) as f:
        catalog = json.load(f)

    existing_plugins = set(catalog.get("plugins", {}).keys())
    print(f"Existing curated plugins: {len(existing_plugins)}")

    # Step 1: Update download stats for ALL existing curated plugins
    print("\nFetching download stats for curated plugins...")
    stats_data = fetch_stats_batch(existing_plugins)
    updated_stats = 0
    for name, stats in stats_data.items():
        if name in catalog["plugins"]:
            catalog["plugins"][name]["downloads"] = {
                "last_day": stats.get("last_day", 0),
                "last_week": stats.get("last_week", 0),
                "last_month": stats.get("last_month", 0),
            }
            updated_stats += 1
    print(f"Updated download stats for {updated_stats} plugins")

    # Step 2: Update version constraints from README for plugins missing them
    plugins_missing_versions = [
        name
        for name, data in catalog["plugins"].items()
        if not data.get("netbox_min_version") and not data.get("netbox_max_version")
    ]
    if plugins_missing_versions:
        print(f"\nChecking READMEs for {len(plugins_missing_versions)} plugins missing version constraints...")
        updated_versions = 0
        for name in plugins_missing_versions:
            info = get_package_info(name)
            if info:
                version_info = parse_netbox_version_from_readme(
                    info.get("description", ""), info.get("version", "")
                )
                if version_info:
                    catalog["plugins"][name]["netbox_min_version"] = version_info.get(
                        "min_version", ""
                    )
                    if version_info.get("max_version"):
                        catalog["plugins"][name]["netbox_max_version"] = version_info[
                            "max_version"
                        ]
                    updated_versions += 1
                    print(f"  {name}: min={version_info.get('min_version', '')} max={version_info.get('max_version', '')}")
            # Rate limit
            time.sleep(0.5)
        print(f"Updated version constraints for {updated_versions} plugins")

    # Step 3: Find and auto-add new popular packages
    all_packages = get_all_netbox_packages()
    new_packages = [p for p in all_packages if p not in existing_plugins]
    print(f"\nNew packages not in catalog: {len(new_packages)}")

    # Fetch stats for new packages
    print("Checking download stats for new packages...")
    new_stats = fetch_stats_batch(new_packages)

    added = []
    for pkg in new_packages:
        stats = new_stats.get(pkg, {})
        monthly = stats.get("last_month", 0)

        if monthly >= MIN_DOWNLOADS_FOR_AUTO_ADD:
            info = get_package_info(pkg)
            summary = info.get("summary", "")
            print(f"  Adding {pkg} ({monthly} downloads/mo): {summary}")

            # Try to extract NetBox version from README
            version_info = parse_netbox_version_from_readme(
                info.get("description", ""), info.get("version", "")
            )
            min_ver = version_info.get("min_version", "")
            max_ver = version_info.get("max_version") or None
            if min_ver:
                print(f"    README version constraints: min={min_ver} max={max_ver}")

            catalog["plugins"][pkg] = {
                "category": "Other",
                "tags": [],
                "certification": "untested",
                "netbox_min_version": min_ver,
                "netbox_max_version": max_ver,
                "notes": summary,
                "recommended": True,
                "documentation_url": info.get("home_page", "")
                or (info.get("project_urls") or {}).get("Homepage", ""),
                "downloads": {
                    "last_day": stats.get("last_day", 0),
                    "last_week": stats.get("last_week", 0),
                    "last_month": monthly,
                },
            }
            added.append(pkg)

    # Update timestamp
    catalog["last_updated"] = date.today().isoformat()

    # Sort plugins alphabetically
    catalog["plugins"] = dict(sorted(catalog["plugins"].items()))

    # Write back
    with open(CATALOG_PATH, "w") as f:
        json.dump(catalog, f, indent=4)
        f.write("\n")

    print(f"\nCatalog updated: {date.today().isoformat()}")
    print(f"Total curated plugins: {len(catalog['plugins'])}")
    print(f"Download stats updated: {updated_stats}")
    if added:
        print(f"Auto-added {len(added)} new plugins: {', '.join(added)}")
    else:
        print("No new plugins met the download threshold")

    return len(added)


if __name__ == "__main__":
    added_count = update_catalog()
    sys.exit(0)
