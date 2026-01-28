from netbox.plugins import PluginMenu, PluginMenuItem

menu = PluginMenu(
    label="Plugin Catalog",
    groups=(
        (
            "Catalog",
            (
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
            ),
        ),
    ),
    icon_class="mdi mdi-puzzle",
)
