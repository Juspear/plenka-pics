"""Автоудаление: python manage.py cleanup_posts [--dry-run]

Запускать раз в сутки по cron, например:
    15 4 * * *  cd /srv/photohost && venv/bin/python manage.py cleanup_posts
"""
import os
import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from photos.models import Post


class Command(BaseCommand):
    help = "Удаляет посты, которые давно никто не открывал, и мусор после сбоев."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Только показать, что будет удалено")

    def handle(self, *args, dry_run=False, **opts):
        now = timezone.now()
        link_cut = now - timedelta(days=settings.AUTODELETE_LINK_DAYS)
        public_cut = now - timedelta(days=settings.AUTODELETE_PUBLIC_DAYS)
        failed_cut = now - timedelta(days=settings.AUTODELETE_FAILED_DAYS)

        # Если пост ни разу не открывали, считаем от даты загрузки
        qs = Post.objects.annotate(seen=Coalesce("last_viewed_at", "created_at")).filter(
            Q(status=Post.Status.READY, visibility=Post.Visibility.LINK, seen__lt=link_cut)
            | Q(status=Post.Status.READY, visibility=Post.Visibility.PUBLIC, seen__lt=public_cut)
            | Q(status=Post.Status.FAILED, created_at__lt=failed_cut)
        )

        count, freed = 0, 0
        for post in qs.iterator():
            for f in (post.media, post.thumb):
                if f:
                    try:
                        freed += f.size
                    except Exception:
                        pass
            if not dry_run:
                post.delete_files()
                post.delete()
            count += 1

        tmp_removed = self._clean_tmp(dry_run)
        verb = "Будет удалено" if dry_run else "Удалено"
        self.stdout.write(f"{verb} постов: {count}, освободится {freed / 1048576:.1f} МБ; "
                          f"временных файлов: {tmp_removed}")

    def _clean_tmp(self, dry_run):
        """Файлы, оставшиеся после прерванной обработки видео (старше суток)."""
        removed, tmp = 0, settings.VIDEO_TMP_DIR
        if not os.path.isdir(tmp):
            return 0
        for name in os.listdir(tmp):
            path = os.path.join(tmp, name)
            if os.path.isfile(path) and time.time() - os.path.getmtime(path) > 86400:
                if not dry_run:
                    os.remove(path)
                removed += 1
        return removed
