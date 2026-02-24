from django.urls import path

from . import views

urlpatterns = [
    # Catalog views
    path("", views.CatalogListView.as_view(), name="catalog_list"),
    path("refresh/", views.RefreshCacheView.as_view(), name="refresh_cache"),
    # Plugin views
    path("plugin/<str:name>/", views.PluginDetailView.as_view(), name="plugin_detail"),
    path(
        "plugin/<str:name>/install/",
        views.PluginInstallView.as_view(),
        name="plugin_install",
    ),
    path(
        "plugin/<str:name>/installed/",
        views.PluginInstalledView.as_view(),
        name="plugin_installed",
    ),
    # Installation log views
    path(
        "history/", views.InstallationLogListView.as_view(), name="installationlog_list"
    ),
    path(
        "history/backfill/",
        views.BackfillExternalView.as_view(),
        name="backfill_external",
    ),
    path(
        "history/<int:pk>/", views.InstallationLogView.as_view(), name="installationlog"
    ),
    path(
        "history/<int:pk>/delete/",
        views.InstallationLogDeleteView.as_view(),
        name="installationlog_delete",
    ),
    path(
        "history/delete/",
        views.InstallationLogBulkDeleteView.as_view(),
        name="installationlog_bulk_delete",
    ),
]
