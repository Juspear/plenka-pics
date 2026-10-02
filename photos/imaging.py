"""Проверка и очистка загруженных картинок.

Файл всегда перекодируется заново: так из него пропадают EXIF
(включая GPS-координаты) и всё, что не является пикселями.
"""
from dataclasses import dataclass
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 40_000_000  # защита от «декомпрессионных бомб»

FORMATS = {  # входной формат -> (выходной формат, расширение)
    "JPEG": ("JPEG", "jpg"),
    "MPO": ("JPEG", "jpg"),   # так Pillow видит часть фото с телефонов
    "PNG": ("PNG", "png"),
    "WEBP": ("WEBP", "webp"),
}
SAVE_PARAMS = {
    "JPEG": {"quality": 90, "optimize": True},
    "PNG": {"optimize": True},
    "WEBP": {"quality": 90},
}
THUMB_SIZE = (480, 480)


@dataclass
class Processed:
    main: ContentFile
    thumb: ContentFile
    ext: str
    width: int
    height: int


def _has_alpha(img):
    return img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)


def _encode(img, fmt, **params):
    buf = BytesIO()
    img.save(buf, fmt, exif=b"", **params)  # exif=b"" — метаданные не пишем
    return ContentFile(buf.getvalue())


def process_image(upload) -> Processed:
    try:
        upload.seek(0)
        with Image.open(upload) as probe:
            probe.verify()
        upload.seek(0)
        img = Image.open(upload)
        img.load()
    except Image.DecompressionBombError:
        raise ValidationError("Слишком большое разрешение: максимум 40 мегапикселей.")
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValidationError("Файл не похож на изображение или повреждён.")

    if img.width * img.height > Image.MAX_IMAGE_PIXELS:
        raise ValidationError("Слишком большое разрешение: максимум 40 мегапикселей.")
    if img.format not in FORMATS:
        raise ValidationError("Поддерживаются только JPEG, PNG и WebP.")
    out_format, ext = FORMATS[img.format]

    img = ImageOps.exif_transpose(img)  # повернуть по EXIF до того, как его выкинуть
    # Цветовой профиль оставляем только для RGB: профиль CMYK или ч/б на RGB-картинке исказит цвета
    icc = img.info.get("icc_profile") if img.mode in ("RGB", "RGBA") else None
    img.info = {}

    if img.mode in ("I;16", "I;16B", "I;16L", "I"):   # 16-битные PNG: сжимаем диапазон до 8 бит
        img = img.convert("I").point(lambda v: v * (1 / 256)).convert("L")

    if out_format == "JPEG":
        img = img.convert("RGB")
    else:
        img = img.convert("RGBA" if _has_alpha(img) else "RGB")

    params = dict(SAVE_PARAMS[out_format])
    if icc:
        params["icc_profile"] = icc
    main = _encode(img, out_format, **params)

    thumb_img = img.copy()
    thumb_img.thumbnail(THUMB_SIZE)
    thumb = _encode(thumb_img, "WEBP", quality=80)

    return Processed(main, thumb, ext, img.width, img.height)


def make_thumb_from_path(path) -> ContentFile:
    """Превью для видео из кадра-постера."""
    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail(THUMB_SIZE)
        return _encode(img, "WEBP", quality=80)


def looks_like_image(upload) -> bool:
    try:
        upload.seek(0)
        with Image.open(upload) as probe:
            ok = probe.format in FORMATS
        upload.seek(0)
        return ok
    except Exception:
        upload.seek(0)
        return False
