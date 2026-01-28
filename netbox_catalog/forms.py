from django import forms
from netbox.forms import NetBoxModelFilterSetForm

from .models import InstallationLog


class PluginFilterForm(forms.Form):
    """Filter form for plugin catalog."""

    q = forms.CharField(
        required=False,
        label="Search",
        widget=forms.TextInput(
            attrs={"placeholder": "Search plugins...", "class": "form-control"}
        ),
    )
    category = forms.ChoiceField(
        required=False, widget=forms.Select(attrs={"class": "form-select"})
    )
    certification = forms.ChoiceField(
        required=False,
        choices=[
            ("", "All Certifications"),
            ("certified", "Certified"),
            ("compatible", "Compatible"),
            ("untested", "Untested"),
            ("deprecated", "Deprecated"),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[
            ("", "All Status"),
            ("installed", "Installed"),
            ("not_installed", "Not Installed"),
            ("activated", "Activated"),
            ("upgradable", "Upgrade Available"),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    compatibility = forms.ChoiceField(
        required=False,
        choices=[
            ("", "All"),
            ("compatible", "Compatible"),
            ("incompatible", "Incompatible"),
            ("unknown", "Unknown"),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    show_uncurated = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, categories=None, **kwargs):
        super().__init__(*args, **kwargs)
        if categories:
            self.fields["category"].choices = [("", "All Categories")] + [
                (c, c) for c in categories
            ]


class InstallForm(forms.Form):
    """Form for installing a plugin."""

    version = forms.CharField(
        required=False,
        label="Version",
        help_text="Leave empty to install latest version",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    confirm = forms.BooleanField(
        required=True,
        label="I understand that I need to edit configuration.py and restart NetBox",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class InstallationLogFilterForm(NetBoxModelFilterSetForm):
    """Filter form for installation logs."""

    model = InstallationLog

    package_name = forms.CharField(
        required=False, widget=forms.TextInput(attrs={"class": "form-control"})
    )
    action = forms.ChoiceField(
        required=False,
        choices=[("", "All")] + list(InstallationLog.Action.choices),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All")] + list(InstallationLog.Status.choices),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
