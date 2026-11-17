from netbox.plugins import PluginConfig

__version__ = "0.4.1"


class NetBoxCatalogConfig(PluginConfig):
    name = "netbox_catalog"
    verbose_name = "Plugin Catalog"
    description = "Browse and install third-party NetBox plugins"
    version = __version__
    author = "Jeremy Worden"
    author_email = "sieteunoseis@gmail.com"
    base_url = "catalog"
    min_version = "4.0.0"

    default_settings = {
        "top_level_menu": True,
        "pypi_cache_timeout": 3600,  # Cache PyPI data for 1 hour
        "catalog_json_url": "",  # Optional: remote catalog.json URL
        "allow_install": True,  # Enable/disable pip install feature
        "show_uncurated": True,  # Show plugins not in curated list
        "pypi_index_url": "https://pypi.org",  # PyPI mirror support
        "superuser_only": True,  # Restrict all views to superusers
    }


config = NetBoxCatalogConfig
