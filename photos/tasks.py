"""Фоновая обработка видео.

Для старта — простой пул потоков внутри процесса Django.
Для продакшена лучше Celery или RQ: здесь задачи теряются при перезапуске сервера.
"""
import logging
import os
import shutil
from concurrent.futures import ThreadPoolExecutor

from django.core.files import File
from django.db import close_old_connections

from .imaging import make_thumb_from_path
from .video import transcode

log = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=1)  # одно видео за раз, чтобы не положить сервер


def enqueue_video(post_id: int, src_path: str):
    _executor.submit(_process_video, post_id, src_path)


def _process_video(post_id: int, src_path: str):
    from .models import Post
    workdir = None
    try:
        post = Post.objects.get(pk=post_id)
        out, poster, info = transcode(src_path)
        workdir = os.path.dirname(out)
        with open(out, "rb") as f:
            post.media.save("v.mp4", File(f), save=False)
        post.thumb.save("t.webp", make_thumb_from_path(poster), save=False)
        # update(), а не save(): если пост удалили, пока шла обработка,
        # save() создал бы его заново
        updated = Post.objects.filter(pk=post_id, status=Post.Status.PROCESSING).update(
            media=post.media.name, thumb=post.thumb.name,
            width=info.width, height=info.height, duration=info.duration,
            status=Post.Status.READY,
        )
        if not updated:
            post.delete_files()
    except Post.DoesNotExist:
        pass   # пост удалили до начала обработки
    except Exception:
        log.exception("Video processing failed for post %s", post_id)
        Post.objects.filter(pk=post_id).update(status=Post.Status.FAILED)
    finally:
        for path in (src_path,):
            try:
                os.remove(path)
            except OSError:
                pass
        if workdir:
            shutil.rmtree(workdir, ignore_errors=True)
        close_old_connections()
