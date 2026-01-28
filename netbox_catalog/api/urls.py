from netbox.api.routers import NetBoxRouter

from . import views

router = NetBoxRouter()
router.register("installation-logs", views.InstallationLogViewSet)

urlpatterns = router.urls
