import hashlib
import os
import time
import secrets
import shutil
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.forms import AuthenticationForm
from django.db.models import F, Q
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import UploadForm
from .imaging import looks_like_image, process_image
from .models import Post
from .tasks import enqueue_video
from .video import probe

MB = 1024 * 1024


# ---------- «свои» посты без аккаунтов ----------
# Список своих постов хранится в сессии (cookie живёт год).
# Запасной вариант — секретная ссылка управления ?key=..., как deletehash у Imgur.

def _owned_ids(request):
    return request.session.get("owned", [])


def _prune_owned(request):
    """Убираем из списка посты, которых уже нет (удалены админом)."""
    owned = _owned_ids(request)
    if owned:
        alive = set(Post.objects.filter(pk__in=owned).values_list("pk", flat=True))
        if len(alive) != len(owned):
            request.session["owned"] = [pk for pk in owned if pk in alive]
    return _owned_ids(request)


def _remember(request, post):
    owned = _owned_ids(request)
    if post.pk not in owned:
        request.session["owned"] = ([post.pk] + owned)[:500]   # сессия не растёт бесконечно


def _forget(request, post_pk):
    request.session["owned"] = [pk for pk in _owned_ids(request) if pk != post_pk]


def _is_owner(request, post):
    return post.pk in _owned_ids(request)


def _own_post_or_404(request, slug):
    post = get_object_or_404(Post, slug=slug)
    if not _is_owner(request, post):
        raise Http404
    return post


# ---------- служебное ----------

def _client_ip(request):
    """IP посетителя. За nginx берём X-Real-IP, который выставляет сам nginx.
    X-Forwarded-For не используем: его первую часть присылает клиент и может подделать,
    обходя все лимиты (вход в админку, загрузки, жалобы)."""
    if settings.TRUST_X_FORWARDED_FOR:
        real = request.META.get("HTTP_X_REAL_IP", "").strip()
        if real:
            return real
    return request.META.get("REMOTE_ADDR", "")


def _client_hash(request):
    return hashlib.sha256(f"{_client_ip(request)}:{settings.SECRET_KEY}".encode()).hexdigest()[:32]


def _rate_limited(client_hash):
    key = f"uploads:{client_hash}"
    if cache.add(key, 1, 3600):
        return False
    try:
        count = cache.incr(key)
    except ValueError:          # ключ успел истечь
        cache.set(key, 1, 3600)
        return False
    return count > settings.UPLOADS_PER_HOUR


def _no_index(response, post):
    if not post.is_public:
        response["X-Robots-Tag"] = "noindex, nofollow"
        response["Cache-Control"] = "private, no-store"
    return response


def _signed_url(file, expire):
    try:
        return file.storage.url(file.name, expire=expire)   # S3: подписанная ссылка на нужный срок
    except TypeError:
        return file.url                                      # локальная разработка


# ---------- страницы ----------

def _home(request, tab="feed", form=None, status=200):
    """Главная: загрузка сверху, ниже вкладки «Лента» и «Мои»."""
    owned = _prune_owned(request)
    if tab == "mine":
        qs = Post.objects.filter(pk__in=owned)
    elif tab == "reports":
        qs = Post.objects.filter(Q(reports__gt=0) | Q(hidden_by_admin=True)).order_by("-reports", "-created_at")
    else:
        qs = Post.objects.filter(
            visibility=Post.Visibility.PUBLIC, status=Post.Status.READY, hidden_by_admin=False
        )
    page = Paginator(qs, 30).get_page(request.GET.get("page"))
    return render(request, "photos/home.html", {
        "page": page, "tab": tab, "upload_form": form or UploadForm(),
        "mine_count": len(owned),
        "reports_count": _reports_count() if request.user.is_staff else 0,
    }, status=status)


def _reports_count():
    return Post.objects.filter(Q(reports__gt=0) | Q(hidden_by_admin=True)).count()


def feed(request):
    return _home(request, "feed")


def mine(request):
    return _home(request, "mine")


def reports(request):
    if not request.user.is_staff:
        raise Http404
    return _home(request, "reports")


# ---------- вход для админа ----------

class StaffLoginForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Неверный логин или пароль.",
    }

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise ValidationError("Неверный логин или пароль.", code="invalid_login")


def _safe_next(request):
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return nxt
    return None


def staff_login(request):
    if request.user.is_staff:
        return redirect(_safe_next(request) or "photos:reports")
    form = StaffLoginForm(request, data=request.POST or None)
    if request.method == "POST":
        ip_key = f"login-fails-ip:{_client_hash(request)}"
        username = (request.POST.get("username") or "").strip().lower()[:150]
        user_key = "login-fails-user:" + hashlib.sha256(username.encode()).hexdigest()[:32]
        # Лимит и по IP, и по логину: перебор с разных IP тоже упрётся в стену
        if (cache.get(ip_key, 0) >= settings.LOGIN_ATTEMPTS
                or cache.get(user_key, 0) >= settings.LOGIN_ATTEMPTS_PER_USER):
            return render(request, "photos/login.html",
                          {"form": StaffLoginForm(request), "locked": True, "next": _safe_next(request)},
                          status=429)
        if form.is_valid():
            cache.delete_many([ip_key, user_key])
            auth_login(request, form.get_user())
            return redirect(_safe_next(request) or "photos:reports")
        cache.set(ip_key, cache.get(ip_key, 0) + 1, 15 * 60)
        cache.set(user_key, cache.get(user_key, 0) + 1, 60 * 60)
        time.sleep(1)   # замедляем перебор
    return render(request, "photos/login.html", {"form": form, "next": _safe_next(request)})


@require_POST
def staff_logout(request):
    owned, reported = _owned_ids(request), request.session.get("reported", [])
    auth_logout(request)   # выход очищает сессию — возвращаем список «своих» постов
    request.session["owned"], request.session["reported"] = owned, reported
    return redirect("photos:feed")


def post_detail(request, slug):
    post = get_object_or_404(Post, slug=slug)

    key = request.GET.get("key")
    if key:
        if secrets.compare_digest(key, post.manage_key):
            _remember(request, post)
            messages.success(request, "Теперь этим постом можно управлять с этого устройства.")
        return redirect(post)   # убираем ключ из адресной строки

    is_owner = _is_owner(request, post)
    if post.hidden_by_admin and not (is_owner or request.user.is_staff):
        raise Http404

    # Обработка зависла (например, сервер перезапустился) — честно показываем ошибку
    stuck_after = timedelta(seconds=settings.VIDEO_TRANSCODE_TIMEOUT + 300)
    if post.status == Post.Status.PROCESSING and timezone.now() - post.created_at > stuck_after:
        Post.objects.filter(pk=post.pk, status=Post.Status.PROCESSING).update(status=Post.Status.FAILED)
        post.status = Post.Status.FAILED

    _count_view(request, post)
    manage_url = request.build_absolute_uri(post.get_manage_url()) if is_owner else ""
    response = render(request, "photos/post.html", {
        "post": post, "is_owner": is_owner, "manage_url": manage_url,
        "already_reported": post.pk in request.session.get("reported", []),
    })
    return _no_index(response, post)


def _count_view(request, post):
    """+1 просмотр. Обновление страницы и повторы с того же IP в течение
    VIEW_DEDUPE_HOURS не считаются, админ не считается."""
    if request.user.is_staff or not post.is_ready:
        return
    key = f"view:{post.pk}:{_client_hash(request)}"
    if cache.add(key, 1, settings.VIEW_DEDUPE_HOURS * 3600):
        now = timezone.now()
        Post.objects.filter(pk=post.pk).update(views=F("views") + 1, last_viewed_at=now)
        post.views += 1
        post.last_viewed_at = now


def media_file(request, slug, kind="full"):
    """Постоянная ссылка на файл. Перенаправляет на подписанный URL хранилища."""
    post = get_object_or_404(Post, slug=slug)
    if not post.is_ready or (post.hidden_by_admin and not (request.user.is_staff or _is_owner(request, post))):
        raise Http404
    file = post.thumb if kind == "thumb" else post.media
    expire = settings.VIDEO_URL_EXPIRE if post.is_video and kind != "thumb" else settings.IMAGE_URL_EXPIRE
    if settings.MEDIA_X_ACCEL:
        # Файлы на диске сервера отдаёт nginx, но только после проверок выше.
        # Прямого адреса у файлов нет, поэтому скрытые и удалённые посты не утекут.
        response = HttpResponse()
        response["X-Accel-Redirect"] = "/_protected/" + file.name
        del response["Content-Type"]   # тип по расширению выставит nginx
    else:
        response = HttpResponseRedirect(_signed_url(file, expire))
    response["Cache-Control"] = "private, max-age=300"
    return _no_index(response, post)


@require_POST
def upload(request):
    form = UploadForm(request.POST, request.FILES)
    if form.is_valid():
        client = _client_hash(request)
        if _rate_limited(client):
            form.add_error("media", "Слишком много загрузок. Попробуй через час.")
        else:
            try:
                post = _create_post(form, client)
            except ValidationError as e:
                form.add_error("media", e)
            else:
                _remember(request, post)
                if post.is_video:
                    messages.success(request, "Видео загружено, обрабатываем. Обычно это занимает до минуты.")
                return redirect(post)
    return _home(request, "feed", form=form, status=400)


def _create_post(form, client_hash):
    f = form.cleaned_data["media"]
    post = Post(
        title=form.cleaned_data["title"],
        visibility=form.cleaned_data["visibility"],
        uploader_hash=client_hash,
    )

    if looks_like_image(f):
        if f.size > settings.MAX_IMAGE_MB * MB:
            raise ValidationError(f"Фото больше {settings.MAX_IMAGE_MB} МБ.")
        result = process_image(f)
        post.kind = Post.Kind.IMAGE
        post.width, post.height = result.width, result.height
        post.media.save(f"x.{result.ext}", result.main, save=False)
        post.thumb.save("x.webp", result.thumb, save=False)
        post.save()
        return post

    # Не картинка — пробуем как видео
    if f.size > settings.MAX_VIDEO_MB * MB:
        raise ValidationError(f"Видео больше {settings.MAX_VIDEO_MB} МБ.")
    os.makedirs(settings.VIDEO_TMP_DIR, exist_ok=True)
    tmp_path = os.path.join(settings.VIDEO_TMP_DIR, uuid.uuid4().hex)
    with open(tmp_path, "wb") as dst:
        f.seek(0)
        shutil.copyfileobj(f, dst, 1024 * 1024)
    try:
        info = probe(tmp_path)
    except ValidationError:
        os.remove(tmp_path)
        raise ValidationError("Поддерживаются фото (JPEG, PNG, WebP) и видео (MP4, MOV, WebM).")

    post.kind = Post.Kind.VIDEO
    post.status = Post.Status.PROCESSING
    post.width, post.height, post.duration = info.width, info.height, info.duration
    post.save()
    enqueue_video(post.pk, tmp_path)
    return post


@require_POST
def post_update(request, slug):
    post = _own_post_or_404(request, slug)
    visibility = request.POST.get("visibility")
    if visibility in Post.Visibility.values:
        post.visibility = visibility
    post.title = request.POST.get("title", "")[:140]
    post.save(update_fields=["visibility", "title"])
    messages.success(request, "Сохранено.")
    return redirect(post)


@require_POST
def post_reset_link(request, slug):
    post = _own_post_or_404(request, slug)
    post.regenerate_slug()
    post.save(update_fields=["slug"])
    messages.success(request, "Ссылка обновлена. Старая больше не работает.")
    return redirect(post)


@require_POST
def post_delete(request, slug):
    post = _own_post_or_404(request, slug)
    pk = post.pk
    post.delete_files()
    post.delete()
    _forget(request, pk)
    messages.success(request, "Пост удалён.")
    return redirect("photos:mine")


@require_POST
def post_report(request, slug):
    post = get_object_or_404(Post, slug=slug)
    reported = request.session.get("reported", [])
    # Одна жалоба с одного IP на пост: иначе любой, почистив cookie, скроет чужой пост
    ip_key = f"report:{post.pk}:{_client_hash(request)}"
    if (post.pk not in reported and not _is_owner(request, post) and not request.user.is_staff
            and cache.add(ip_key, 1, 30 * 24 * 3600)):
        # F() — чтобы одновременные жалобы не затирали друг друга
        Post.objects.filter(pk=post.pk).update(reports=F("reports") + 1)
        post.refresh_from_db(fields=["reports"])
        if post.reports >= settings.REPORTS_TO_HIDE and not post.hidden_by_admin:
            Post.objects.filter(pk=post.pk).update(hidden_by_admin=True)   # скрываем до проверки
            post.hidden_by_admin = True
        request.session["reported"] = reported + [post.pk]
    messages.success(request, "Спасибо, жалоба отправлена.")
    return redirect("photos:feed") if post.hidden_by_admin else redirect(post)


@require_POST
def moderate(request, slug):
    """Действия админа прямо со страницы поста."""
    if not request.user.is_staff:
        raise Http404
    post = get_object_or_404(Post, slug=slug)
    action = request.POST.get("action")
    if action == "hide":
        post.hidden_by_admin = True
        post.save(update_fields=["hidden_by_admin"])
        messages.success(request, "Пост скрыт.")
    elif action == "approve":
        post.hidden_by_admin, post.reports = False, 0
        post.save(update_fields=["hidden_by_admin", "reports"])
        messages.success(request, "Пост оставлен, жалобы сброшены.")
    elif action == "delete":
        post.delete_files()
        post.delete()
        messages.success(request, "Пост удалён.")
        return redirect("photos:reports")
    return redirect(post)
