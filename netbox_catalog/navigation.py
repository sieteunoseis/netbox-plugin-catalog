from django.conf import settings

from netbox.plugins import PluginMenu, PluginMenuItem


def _get_menu():
    """Build menu, requiring superuser when superuser_only is enabled."""
    config = settings.PLUGINS_CONFIG.get("netbox_catalog", {})
    superuser_only = config.get("superuser_only", True)

    # When superuser_only is True, use a permission that only superusers
    # will have (since we don't assign it to any group).
    perms = ["netbox_catalog.view_installationlog"]
    if superuser_only:
        # Add a non-existent permission — only superusers bypass permission checks
        perms.append("netbox_catalog.superuser_required")

    return PluginMenu(
        label="Plugin Catalog",
        groups=(
            (
                "Catalog",
                (
                    PluginMenuItem(
                        link="plugins:netbox_catalog:catalog_list",
                        link_text="Browse Plugins",
                        permissions=perms,
                    ),
                    PluginMenuItem(
                        link="plugins:netbox_catalog:installationlog_list",
                        link_text="Installation History",
                        permissions=perms,
                    ),
                ),
            ),
        ),
        icon_class="mdi mdi-puzzle",
    )


menu = _get_menu()
