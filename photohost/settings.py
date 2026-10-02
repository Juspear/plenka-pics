import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# настройки — в .env рядом с manage.py
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

env = os.environ.get

# по умолчанию боевой режим; для разработки DEBUG=1
DEBUG = env("DEBUG", "0") == "1"
SECRET_KEY = env("SECRET_KEY", "dev-only-change-me" if DEBUG else "")
if not SECRET_KEY:
    raise RuntimeError("Задай переменную окружения SECRET_KEY (или DEBUG=1 для разработки).")
ALLOWED_HOSTS = env("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
# для https-домена
CSRF_TRUSTED_ORIGINS = [o for o in env("CSRF_TRUSTED_ORIGINS", "").split(",") if o]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "photos",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",   # раздаёт CSS/JS в боевом режиме
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "photohost.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "photos.context_processors.site",
    ]},
}]
WSGI_APPLICATION = "photohost.wsgi.application"

if env("POSTGRES_DB"):
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

# S3_BUCKET → приватный бакет с подписанными ссылками (10 минут)
if env("S3_BUCKET"):
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                "bucket_name": env("S3_BUCKET"),
                "endpoint_url": env("S3_ENDPOINT_URL"),   # R2 / B2 / MinIO
                "access_key": env("S3_ACCESS_KEY"),
                "secret_key": env("S3_SECRET_KEY"),
                "region_name": env("S3_REGION", "auto"),
                "signature_version": "s3v4",
                "querystring_auth": True,      # подписанные URL
                "querystring_expire": 600,     # по умолчанию 10 минут
                "default_acl": None,           # бакет остаётся приватным
                "file_overwrite": False,
            },
        },
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    }
else:
    # в бою файлы отдаёт nginx через X-Accel-Redirect после проверки доступа
    MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))
    MEDIA_URL = "/media/"
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    }

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MAX_IMAGE_MB = 20
MAX_VIDEO_MB = 200
MAX_VIDEO_SECONDS = 5 * 60
VIDEO_TRANSCODE_TIMEOUT = 15 * 60
VIDEO_TMP_DIR = BASE_DIR / "tmp"
UPLOADS_PER_HOUR = 30            # с одного IP
REPORTS_TO_HIDE = 5              # после стольких жалоб пост скрывается до проверки
IMAGE_URL_EXPIRE = 10 * 60       # подписанные ссылки на фото живут 10 минут
VIDEO_URL_EXPIRE = 3 * 60 * 60   # на видео дольше, чтобы не обрывалось при просмотре
TRUST_X_FORWARDED_FOR = env("TRUST_X_FORWARDED_FOR", "0") == "1"   # включить за nginx (нужен X-Real-IP)
MEDIA_X_ACCEL = env("MEDIA_X_ACCEL", "0") == "1"   # файлы на диске раздаёт nginx (см. README)

# автоудаление, команда cleanup_posts (раз в сутки)
AUTODELETE_LINK_DAYS = 90        # пост «по ссылке» без просмотров столько дней — удаляется
AUTODELETE_PUBLIC_DAYS = 90      # пост «в ленте» без просмотров столько дней — удаляется
AUTODELETE_FAILED_DAYS = 1       # видео, которое не удалось обработать
VIEW_DEDUPE_HOURS = 6            # повторный просмотр с того же IP раньше этого срока не считается

AUTHOR_URL = "https://github.com/Juspear"   # ссылка на твой GitHub в подвале

LOGIN_URL = "photos:login"
LOGIN_ATTEMPTS = 5               # неудачных попыток входа за 15 минут с одного IP
LOGIN_ATTEMPTS_PER_USER = 10     # неудачных попыток за час на один логин (с любых IP)
# неочевидный адрес админки через ADMIN_URL
ADMIN_URL = env("ADMIN_URL", "admin/").strip("/") + "/"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# кэш на диске, чтобы лимиты были общими для всех процессов gunicorn
CACHES = {"default": {
    "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
    "LOCATION": env("CACHE_DIR", str(BASE_DIR / "cache")),
}}

# свои посты — в сессии, живёт год
SESSION_COOKIE_AGE = 365 * 24 * 60 * 60
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# Токен из ссылки не уходит на другие сайты через Referer
SECURE_REFERRER_POLICY = "no-referrer"
SECURE_CONTENT_TYPE_NOSNIFF = True
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SESSION_COOKIE_NAME = "__Host-sessionid"   # такую cookie нельзя подменить с поддомена
    CSRF_COOKIE_NAME = "__Host-csrftoken"
if TRUST_X_FORWARDED_FOR:
    # за nginx, иначе бесконечный редирект на https
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

LANGUAGE_CODE = "ru"
TIME_ZONE = "Europe/Samara"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
