import django_tables2 as tables

from netbox.tables import NetBoxTable, columns

from .models import InstallationLog


class InstallationLogTable(NetBoxTable):
    """Table for installation logs."""

    package_name = tables.Column(
        linkify=True,
        verbose_name="Package"
    )
    version = tables.Column()
    action = tables.Column()
    status = tables.TemplateColumn(
        template_code='''
        {% if record.status == "success" %}
            <span class="badge text-bg-success">{{ record.get_status_display }}</span>
        {% elif record.status == "failed" %}
            <span class="badge text-bg-danger">{{ record.get_status_display }}</span>
        {% elif record.status == "in_progress" %}
            <span class="badge text-bg-info">{{ record.get_status_display }}</span>
        {% else %}
            <span class="badge text-bg-secondary">{{ record.get_status_display }}</span>
        {% endif %}
        '''
    )
    user = tables.Column()
    started = columns.DateTimeColumn()
    completed = columns.DateTimeColumn()
    actions = columns.ActionsColumn(actions=("delete",))

    class Meta(NetBoxTable.Meta):
        model = InstallationLog
        fields = (
            "pk", "package_name", "version", "action", "status",
            "user", "started", "completed", "actions"
        )
        default_columns = (
            "package_name", "version", "action", "status", "user", "started"
        )
