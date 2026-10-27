"""Custom template filters for the expense tracker."""

from django import template

register = template.Library()


@register.filter
def get_color(color_map, category):
    """Look up a category color from the color_map dict.

    Usage: {{ color_map|get_color:exp.category }}
    """
    if isinstance(color_map, dict):
        return color_map.get(category, '#6b7280')
    return '#6b7280'


@register.filter
def get_color_bg(color_map, category):
    """Return category color with '18' suffix for background transparency.

    Usage: {{ color_map|get_color_bg:exp.category }}
    """
    if isinstance(color_map, dict):
        color = color_map.get(category, '#6b7280')
        return f"{color}18"
    return '#6b728018'
