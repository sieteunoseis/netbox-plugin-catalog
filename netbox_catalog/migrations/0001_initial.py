import django.db.models.deletion
import utilities.json
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="InstallationLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                (
                    "package_name",
                    models.CharField(help_text="PyPI package name", max_length=255),
                ),
                (
                    "version",
                    models.CharField(
                        blank=True,
                        help_text="Version installed or attempted",
                        max_length=50,
                    ),
                ),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("install", "Install"),
                            ("upgrade", "Upgrade"),
                            ("uninstall", "Uninstall"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("in_progress", "In Progress"),
                            ("success", "Success"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "output",
                    models.TextField(blank=True, help_text="pip command output"),
                ),
                (
                    "error",
                    models.TextField(blank=True, help_text="Error message if failed"),
                ),
                ("started", models.DateTimeField(auto_now_add=True)),
                ("completed", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="plugin_installations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Installation Log",
                "verbose_name_plural": "Installation Logs",
                "ordering": ["-started"],
            },
        ),
    ]
