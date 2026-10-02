from urllib.parse import urlencode

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, reverse
from django.views.generic import RedirectView


class AdminLoginRedirect(RedirectView):
    """У стандартной админки Django нет защиты от перебора паролей,
    поэтому её страница входа ведёт на наш /login/ с лимитами попыток."""
    def get_redirect_url(self, *args, **kwargs):
        nxt = self.request.GET.get("next", "/" + settings.ADMIN_URL)
        return reverse("photos:login") + "?" + urlencode({"next": nxt})


urlpatterns = [
    path(settings.ADMIN_URL + "login/", AdminLoginRedirect.as_view()),
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("photos.urls")),
]
if settings.DEBUG and hasattr(settings, "MEDIA_ROOT"):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
