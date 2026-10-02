"""Проверка и перекодирование видео через ffmpeg.

Видео всегда перекодируется в H.264/AAC MP4:
  * играет в любом браузере и на телефоне;
  * из файла удаляются все метаданные (у телефонов там бывают GPS-координаты);
  * размер ограничивается до 1920 px по длинной стороне.
"""
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ValidationError

FFMPEG = getattr(settings, "FFMPEG_BIN", "ffmpeg")
FFPROBE = getattr(settings, "FFPROBE_BIN", "ffprobe")


# Разрешённые контейнеры. Всё остальное (плейлисты HLS, concat и т.п.) отклоняем:
# такие «видео» могут заставить ffmpeg читать файлы сервера или ходить по сети.
ALLOWED_FORMATS = {"mov", "mp4", "m4a", "3gp", "3g2", "mj2", "matroska", "webm"}


@dataclass
class ProbeResult:
    duration: float
    width: int
    height: int
    demuxer: str = "mov"


def probe(path: str) -> ProbeResult:
    try:
        out = subprocess.run(
            [FFPROBE, "-v", "error", "-protocol_whitelist", "file",
             "-print_format", "json", "-show_streams", "-show_format", path],
            capture_output=True, timeout=30, check=True,
        ).stdout
        info = json.loads(out)
    except (subprocess.SubprocessError, json.JSONDecodeError):
        raise ValidationError("Не удалось прочитать файл. Это точно видео?")

    names = set((info.get("format", {}).get("format_name") or "").split(","))
    if not names or not names <= ALLOWED_FORMATS:
        raise ValidationError("Поддерживаются видео MP4, MOV и WebM.")
    demuxer = "matroska" if "matroska" in names else "mov"

    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video:
        raise ValidationError("В файле нет видеодорожки.")
    duration = float(info.get("format", {}).get("duration") or video.get("duration") or 0)
    if duration <= 0:
        raise ValidationError("Не удалось определить длительность видео.")
    if duration > settings.MAX_VIDEO_SECONDS:
        raise ValidationError(f"Видео длиннее {settings.MAX_VIDEO_SECONDS // 60} мин.")
    return ProbeResult(duration, int(video.get("width") or 0), int(video.get("height") or 0), demuxer)


def transcode(src: str) -> tuple[str, str, ProbeResult]:
    """Возвращает пути к готовому mp4 и jpeg-постеру во временной папке."""
    demuxer = probe(src).demuxer   # формат проверен ещё раз и задан явно, без автоугадывания
    workdir = tempfile.mkdtemp(prefix="vid-")
    out = os.path.join(workdir, "out.mp4")
    poster = os.path.join(workdir, "poster.jpg")
    scale = "scale='if(gt(iw,ih),min(1920,iw),-2)':'if(gt(iw,ih),-2,min(1920,ih))'"
    subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-protocol_whitelist", "file", "-f", demuxer, "-i", src,
         "-map", "0:v:0", "-map", "0:a:0?",
         "-map_metadata", "-1", "-map_chapters", "-1",
         "-vf", scale, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-ac", "2",
         "-movflags", "+faststart", out],
        check=True, timeout=settings.VIDEO_TRANSCODE_TIMEOUT,
    )
    result = probe(out)
    at = min(1.0, result.duration / 2)
    subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-protocol_whitelist", "file", "-ss", f"{at:.2f}", "-f", "mp4", "-i", out,
         "-frames:v", "1",
         "-vf", "scale='min(960,iw)':-2", "-q:v", "4", poster],
        check=True, timeout=60,
    )
    return out, poster, result
