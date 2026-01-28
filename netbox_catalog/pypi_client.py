import logging
from typing import Optional

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class PyPIClient:
    """Client for fetching NetBox plugins from PyPI."""

    SIMPLE_API = "/simple/"
    JSON_API = "/pypi/{package}/json"
    NETBOX_PREFIXES = ["netbox-", "netbox_"]

    def __init__(self, base_url: str = None, timeout: int = 30):
        plugin_config = getattr(settings, "PLUGINS_CONFIG", {}).get(
            "netbox_catalog", {}
        )
        self.base_url = (
            base_url or plugin_config.get("pypi_index_url", "https://pypi.org")
        ).rstrip("/")
        self.timeout = timeout
        self.cache_timeout = plugin_config.get("pypi_cache_timeout", 3600)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.pypi.simple.v1+json",
                "User-Agent": "netbox-catalog/0.1.0",
            }
        )

    def get_all_netbox_packages(self) -> list[str]:
        """Fetch all package names that start with netbox- prefix."""
        cache_key = "netbox_catalog:pypi_packages"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            response = self.session.get(
                f"{self.base_url}{self.SIMPLE_API}", timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()

            # Filter for netbox-* packages
            packages = [
                p["name"]
                for p in data.get("projects", [])
                if any(
                    p["name"].lower().startswith(prefix)
                    for prefix in self.NETBOX_PREFIXES
                )
            ]

            cache.set(cache_key, packages, self.cache_timeout)
            return packages

        except requests.RequestException as e:
            logger.error(f"Failed to fetch PyPI package list: {e}")
            return []

    def get_package_info(self, package_name: str) -> Optional[dict]:
        """Fetch detailed package info from PyPI JSON API."""
        cache_key = f"netbox_catalog:package:{package_name}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            # Need different Accept header for JSON API
            headers = {
                "Accept": "application/json",
                "User-Agent": "netbox-catalog/0.1.0",
            }
            url = f"{self.base_url}{self.JSON_API.format(package=package_name)}"
            response = requests.get(url, headers=headers, timeout=self.timeout)
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
                "author": info.get("author")
                or self._extract_author_from_email(info.get("author_email")),
                "author_email": info.get("author_email"),
                "license": info.get("license"),
                "keywords": info.get("keywords"),
                "classifiers": info.get("classifiers", []),
                "requires_python": info.get("requires_python"),
                "requires_dist": info.get("requires_dist", []),
                "project_urls": info.get("project_urls", {}),
                "home_page": info.get("home_page")
                or (info.get("project_urls") or {}).get("Homepage"),
                "releases": list(data.get("releases", {}).keys()),
            }

            cache.set(cache_key, package_info, self.cache_timeout)
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

    def clear_cache(self):
        """Clear all cached PyPI data."""
        cache.delete("netbox_catalog:pypi_packages")
        # Note: Individual package caches would need to be tracked to clear
