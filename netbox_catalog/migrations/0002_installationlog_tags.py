import taggit.managers
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("extras", "0134_owner"),
        ("netbox_catalog", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="installationlog",
            name="tags",
            field=taggit.managers.TaggableManager(
                through="extras.TaggedItem", to="extras.Tag"
            ),
        ),
    ]
