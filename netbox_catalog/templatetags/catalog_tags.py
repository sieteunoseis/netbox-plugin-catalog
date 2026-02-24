import markdown as md
from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name="render_markdown")
def render_markdown(value):
    """Render markdown text as HTML."""
    if not value:
        return ""
    html = md.markdown(
        value,
        extensions=["tables", "fenced_code", "toc"],
    )
    return mark_safe(html)


@register.filter(name="render_description")
def render_description(plugin):
    """Render plugin description based on content type."""
    if not plugin.description:
        return ""
    content_type = (plugin.description_content_type or "").lower()
    if "markdown" in content_type or content_type == "":
        # Default to markdown since most PyPI packages use it
        return render_markdown(plugin.description)
    # For RST or plain text, just escape and add line breaks
    return mark_safe(escape(plugin.description).replace("\n", "<br>"))
