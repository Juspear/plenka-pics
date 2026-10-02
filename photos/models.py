import os
import secrets
import string
import uuid

from django.db import models
from django.urls import reverse

ALPHABET = string.ascii_letters + string.digits


def make_slug(length: int = 10) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def make_manage_key() -> str:
    # Секретный ключ управления, как deletehash у Imgur
    return secrets.token_urlsafe(24)


def storage_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"media/{uuid.uuid4().hex}{ext}"


class Post(models.Model):
    class Visibility(models.TextChoices):
        PUBLIC = "public", "В ленте"
        LINK = "link", "По ссылке"

    class Kind(models.TextChoices):
        IMAGE = "image", "Фото"
        VIDEO = "video", "Видео"

    class Status(models.TextChoices):
        PROCESSING = "processing", "Обрабатывается"
        READY = "ready", "Готово"
        FAILED = "failed", "Ошибка"

    slug = models.CharField(max_length=16, unique=True, default=make_slug, editable=False)
    manage_key = models.CharField(max_length=64, default=make_manage_key, editable=False)
    title = models.CharField(max_length=140, blank=True)
    visibility = models.CharField(max_length=8, choices=Visibility.choices, default=Visibility.LINK)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.IMAGE)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.READY)

    media = models.FileField(upload_to=storage_path, blank=True)   # фото или видео (mp4)
    thumb = models.FileField(upload_to=storage_path, blank=True)   # превью для ленты / постер видео
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    duration = models.FloatField(default=0)                        # секунды, только для видео

    # Модерация: хэш IP (не сам IP) и жалобы
    uploader_hash = models.CharField(max_length=64, blank=True, db_index=True)
    reports = models.PositiveIntegerField(default=0)
    hidden_by_admin = models.BooleanField(default=False)

    # Публичная статистика и основа для автоудаления
    views = models.PositiveIntegerField(default=0)
    last_viewed_at = models.DateTimeField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["visibility", "status", "hidden_by_admin", "-created_at"])]

    def __str__(self):
        return self.title or self.slug

    @property
    def is_public(self):
        return self.visibility == self.Visibility.PUBLIC

    @property
    def is_video(self):
        return self.kind == self.Kind.VIDEO

    @property
    def is_ready(self):
        return self.status == self.Status.READY

    @property
    def duration_label(self):
        s = int(round(self.duration))
        return f"{s // 60}:{s % 60:02d}"

    def get_absolute_url(self):
        return reverse("photos:post", args=[self.slug])

    def get_manage_url(self):
        return f"{self.get_absolute_url()}?key={self.manage_key}"

    def regenerate_slug(self):
        new = make_slug()
        while Post.objects.filter(slug=new).exists():
            new = make_slug()
        self.slug = new

    def delete_files(self):
        for f in (self.media, self.thumb):
            if f:
                f.delete(save=False)
