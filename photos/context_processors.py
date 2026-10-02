from django.conf import settings


def _months(days):
    """90 -> «3 месяца», 365 -> «12 месяцев», 10 -> «10 дней»."""
    if days % 30 == 0 or days in (365, 366):
        n = 12 if days in (365, 366) else days // 30
        word = "месяц" if n % 10 == 1 and n % 100 != 11 else \
            "месяца" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "месяцев"
        return f"{n} {word}"
    word = "день" if days % 10 == 1 and days % 100 != 11 else \
        "дня" if days % 10 in (2, 3, 4) and days % 100 not in (12, 13, 14) else "дней"
    return f"{days} {word}"


def site(request):
    link, public = settings.AUTODELETE_LINK_DAYS, settings.AUTODELETE_PUBLIC_DAYS
    if link == public:
        note = f"Посты, которые никто не открывает {_months(link)}, удаляются автоматически."
    else:
        note = (f"Посты без просмотров удаляются автоматически: по ссылке через {_months(link)}, "
                f"в ленте через {_months(public)}.")
    return {"AUTHOR_URL": settings.AUTHOR_URL, "AUTODELETE_NOTE": note}
