from django.contrib.auth import get_user_model
from django.db import models
from django.urls import reverse
from netbox.models import NetBoxModel


class InstallationLog(NetBoxModel):
    """Log of plugin installation attempts."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_PROGRESS = "in_progress", "In Progress"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    class Action(models.TextChoices):
        INSTALL = "install", "Install"
        UPGRADE = "upgrade", "Upgrade"
        UNINSTALL = "uninstall", "Uninstall"

    package_name = models.CharField(max_length=255, help_text="PyPI package name")
    version = models.CharField(
        max_length=50, blank=True, help_text="Version installed or attempted"
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    output = models.TextField(blank=True, help_text="pip command output")
    error = models.TextField(blank=True, help_text="Error message if failed")
    user = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plugin_installations",
    )
    started = models.DateTimeField(auto_now_add=True)
    completed = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started"]
        verbose_name = "Installation Log"
        verbose_name_plural = "Installation Logs"

    def __str__(self):
        return f"{self.get_action_display()} {self.package_name} ({self.get_status_display()})"

    def get_absolute_url(self):
        return reverse("plugins:netbox_catalog:installationlog", args=[self.pk])
