from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("preview", "slug", "title", "kind", "visibility", "status", "views", "last_viewed_at", "reports", "hidden_by_admin", "created_at")
    list_filter = ("hidden_by_admin", "kind", "visibility", "status")
    search_fields = ("title", "slug", "uploader_hash")
    ordering = ("-reports", "-created_at")
    readonly_fields = ("slug", "manage_key", "uploader_hash", "width", "height", "duration", "views", "last_viewed_at", "created_at")
    actions = ["hide", "unhide", "delete_with_files"]

    @admin.display(description="")
    def preview(self, obj):
        if obj.thumb and obj.is_ready:
            # через проверяющий доступ адрес сайта: прямых ссылок на файлы нет
            return format_html('<img src="{}" style="height:48px;border-radius:4px">',
                               reverse("photos:thumb", args=[obj.slug]))
        return "—"

    @admin.action(description="Скрыть")
    def hide(self, request, qs):
        qs.update(hidden_by_admin=True)

    @admin.action(description="Вернуть (сбросить жалобы)")
    def unhide(self, request, qs):
        qs.update(hidden_by_admin=False, reports=0)

    @admin.action(description="Удалить вместе с файлами")
    def delete_with_files(self, request, qs):
        for post in qs:
            post.delete_files()
            post.delete()

    def delete_model(self, request, obj):
        obj.delete_files()
        obj.delete()
