# Как запустить плёнку на VPS

Инструкция для сервера на **Ubuntu 24.04** и домена **plenka-pics.ru**.
Все команды вводятся в Терминале на Mac (на Windows — в PowerShell).
Где написано `ВАШ_IP` — подставь IP-адрес сервера из панели хостинга.

Займёт примерно час. Если на каком-то шаге что-то пошло не так, не иди дальше:
скопируй текст ошибки и спроси.

---

## Шаг 0. Домен смотрит на сервер

В панели, где покупал домен, открой DNS-записи и добавь две **A-записи**:

| Имя | Тип | Значение |
|---|---|---|
| `@` | A | ВАШ_IP |
| `www` | A | ВАШ_IP |

Записи начинают работать от нескольких минут до нескольких часов. Пока ждёшь, делай шаги ниже.

---

## Шаг 1. Подключиться к серверу

```bash
ssh root@ВАШ_IP
```

Первый раз спросит `Are you sure you want to continue connecting?` — напиши `yes`.
Пароль root пришёл на почту или виден в панели хостинга. При вводе пароль не отображается — это нормально.

Все следующие команды выполняются **на сервере**, пока не сказано иначе.

---

## Шаг 2. Обновить систему и поставить всё нужное

```bash
apt update && apt upgrade -y
apt install -y python3-venv python3-dev build-essential libpq-dev \
  postgresql nginx ffmpeg git certbot python3-certbot-nginx ufw
```

Если появится розовое окно про перезапуск служб — просто нажми Enter.

---

## Шаг 3. Файрвол

Открываем только SSH и веб:

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable
```

На вопрос `Proceed with operation?` ответь `y`.

---

## Шаг 4. Файл подкачки (если на сервере 2 ГБ памяти)

Чтобы обработка видео не упёрлась в память:

```bash
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

Проверка: `free -h` — в строке `Swap` должно быть `2.0Gi`.

---

## Шаг 5. База данных

Придумай пароль для базы (длинный, без кавычек) и подставь вместо `ПАРОЛЬ_БАЗЫ`:

```bash
sudo -u postgres psql -c "CREATE USER plenka WITH PASSWORD 'ПАРОЛЬ_БАЗЫ';"
sudo -u postgres psql -c "CREATE DATABASE plenka OWNER plenka;"
```

Должно ответить `CREATE ROLE` и `CREATE DATABASE`. Пароль понадобится на шаге 7.

---

## Шаг 6. Скачать код

```bash
git clone https://github.com/Juspear/plenka-pics.git /srv/photohost
cd /srv/photohost
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt
```

Если репозиторий ещё не на GitHub, можно закинуть архив прямо с ноутбука
(команда выполняется **на Mac**, в новом окне Терминала, из папки, где лежит архив):

```bash
scp plenka-pics.zip root@ВАШ_IP:/root/
```

и потом на сервере:

```bash
apt install -y unzip
cd /root && unzip plenka-pics.zip && mv plenka-pics /srv/photohost
cd /srv/photohost && python3 -m venv venv && venv/bin/pip install -r requirements.txt
```

---

## Шаг 7. Настройки сервера (.env)

Сгенерируй секретный ключ:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

Скопируй результат. Теперь создай файл настроек:

```bash
cp deploy/env.example .env
nano .env
```

Заполни три значения:
- `SECRET_KEY=` — ключ, который только что сгенерировал;
- `POSTGRES_PASSWORD=` — пароль базы из шага 5;
- `ADMIN_URL=` — неочевидный адрес стандартной админки Django, например `panel-k7x2q/`.

Сохранить в nano: `Ctrl+O`, Enter, выйти: `Ctrl+X`.

Закроем файл от посторонних глаз:

```bash
chown root:www-data .env
chmod 640 .env
```

---

## Шаг 8. Подготовить базу, файлы и папки

```bash
cd /srv/photohost
venv/bin/python manage.py makemigrations photos
venv/bin/python manage.py migrate
venv/bin/python manage.py collectstatic --noinput
mkdir -p media tmp cache
chown -R www-data:www-data media tmp cache
```

Если `migrate` завершился без красного текста, всё хорошо.

---

## Шаг 9. Аккаунт админа

Пароль — в одинарных кавычках:

```bash
DJANGO_SUPERUSER_USERNAME='Jusper' DJANGO_SUPERUSER_PASSWORD='ТВОЙ_ПАРОЛЬ' DJANGO_SUPERUSER_EMAIL='' \
  venv/bin/python manage.py createsuperuser --noinput
```

Должно ответить `Superuser created successfully.`
Чтобы пароль не остался в истории команд: `history -c`.

---

## Шаг 10. Запустить сайт как службу

```bash
cp deploy/plenka.service /etc/systemd/system/plenka.service
systemctl daemon-reload
systemctl enable --now plenka
systemctl status plenka
```

В выводе должно быть зелёное `active (running)`. Выйти из просмотра: `q`.

---

## Шаг 11. nginx

```bash
cp deploy/nginx.conf /etc/nginx/sites-available/plenka
ln -s /etc/nginx/sites-available/plenka /etc/nginx/sites-enabled/plenka
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
```

`nginx -t` должен сказать `syntax is ok` и `test is successful`.

---

## Шаг 12. HTTPS

Этот шаг работает, только когда домен уже смотрит на сервер (шаг 0).
Проверить: на Mac выполни `ping plenka-pics.ru` — в ответе должен быть ВАШ_IP.

```bash
certbot --nginx -d plenka-pics.ru -d www.plenka-pics.ru
```

Введи почту (на неё придут напоминания, если с сертификатом что-то не так), согласись с условиями (`Y`).
Сертификат будет продлеваться сам.

Открывай **https://plenka-pics.ru** — сайт должен работать.

> Сайт работает только по HTTPS. По http:// без сертификата формы (загрузка, вход) не отправятся —
> это защита, а не ошибка.

---

## Шаг 13. Автоудаление и очистка по расписанию

```bash
crontab -u www-data -e
```

Если спросит, каким редактором открыть, выбери `1` (nano). В конец файла добавь строку:

```
15 4 * * * cd /srv/photohost && venv/bin/python manage.py cleanup_posts && venv/bin/python manage.py clearsessions
```

Сохрани (`Ctrl+O`, Enter, `Ctrl+X`). Каждую ночь в 4:15 будут удаляться посты без просмотров
и старые сессии. Проверить, что удалится, ничего не трогая:

```bash
cd /srv/photohost && sudo -u www-data venv/bin/python manage.py cleanup_posts --dry-run
```

---

## Шаг 14. Проверка

1. Загрузи фото — должна открыться страница поста.
2. Загрузи короткое видео — сначала «обрабатывается», через несколько секунд появится плеер.
3. Внизу страницы нажми **Admin**, войди как Jusper — должна появиться вкладка «Жалобы».
4. Переключи тему, открой фото на весь экран, скопируй ссылку.

---

## Как обновлять сайт

После изменений в коде (запушил на GitHub):

```bash
cd /srv/photohost
git pull
venv/bin/pip install -r requirements.txt
venv/bin/python manage.py makemigrations photos
venv/bin/python manage.py migrate
venv/bin/python manage.py collectstatic --noinput
systemctl restart plenka
```

---

## Если что-то не работает

| Что видишь | Где смотреть |
|---|---|
| 502 Bad Gateway | `journalctl -u plenka -n 50` — ошибка Django/gunicorn |
| Сайт не открывается вообще | `systemctl status nginx`, проверь DNS (`ping plenka-pics.ru`) |
| Видео висит в «обрабатывается» | `journalctl -u plenka -n 100` |
| Ошибка 400 Bad Request | в `.env` проверь `ALLOWED_HOSTS` |
| Ошибка CSRF при загрузке | открой сайт по https, проверь `CSRF_TRUSTED_ORIGINS` |

После правки `.env` всегда: `systemctl restart plenka`.

---

## Что где лежит на сервере

| Путь | Что это |
|---|---|
| `/srv/photohost` | код сайта |
| `/srv/photohost/.env` | настройки и пароли (в git не попадает) |
| `/srv/photohost/media` | загруженные фото и видео |
| `/etc/nginx/sites-available/plenka` | конфиг nginx |
| `/etc/systemd/system/plenka.service` | служба, которая держит сайт запущенным |

Сменить пароль админа: `cd /srv/photohost && venv/bin/python manage.py changepassword Jusper`.

Поменять лимиты и сроки автоудаления: `photohost/settings.py`, затем `systemctl restart plenka`.
