from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def ago(value):
    """Короткое «сколько прошло»: только что, 5 мин, 3 ч, 2 дн, 4 нед, 3 мес, 2 г."""
    if not value:
        return ""
    s = int((timezone.now() - value).total_seconds())
    if s < 60:
        return "только что"
    for size, unit in ((31536000, "г"), (2592000, "мес"), (604800, "нед"), (86400, "дн"), (3600, "ч"), (60, "мин")):
        if s >= size:
            return f"{s // size} {unit} назад"
    return "только что"


@register.filter
def compact(n):
    """1234 -> «1,2 тыс», 2500000 -> «2,5 млн»."""
    n = int(n or 0)
    if n < 1000:
        return str(n)
    for size, unit in ((1_000_000, "млн"), (1000, "тыс")):
        if n >= size:
            v = n / size
            text = f"{v:.1f}".rstrip("0").rstrip(".").replace(".", ",") if v < 10 else str(int(v))
            return f"{text} {unit}"
