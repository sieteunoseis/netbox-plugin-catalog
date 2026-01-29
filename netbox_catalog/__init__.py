from netbox.plugins import PluginConfig

__version__ = "0.1.3"


class NetBoxCatalogConfig(PluginConfig):
    name = "netbox_catalog"
    verbose_name = "Plugin Catalog"
    description = "Browse and install third-party NetBox plugins"
    version = __version__
    author = "sieteunoseis"
    author_email = "sieteunoseis@gmail.com"
    base_url = "catalog"
    min_version = "4.0.0"

    default_settings = {
        "pypi_cache_timeout": 3600,  # Cache PyPI data for 1 hour
        "catalog_json_url": "",  # Optional: remote catalog.json URL
        "allow_install": True,  # Enable/disable pip install feature
        "show_uncurated": True,  # Show plugins not in curated list
        "pypi_index_url": "https://pypi.org",  # PyPI mirror support
    }


config = NetBoxCatalogConfig
