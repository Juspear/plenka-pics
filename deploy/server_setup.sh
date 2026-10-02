#!/usr/bin/env bash
# Автодеплой plenka-pics. Запускать НА СЕРВЕРЕ от root:  bash deploy/server_setup.sh
set -euo pipefail
APP=/srv/photohost
if [ "$(pwd)" != "$APP" ]; then
  if [ ! -d "$APP" ]; then echo ">> Переношу код в $APP"; mkdir -p "$APP"; cp -a ./. "$APP"/; fi
  cd "$APP"
fi
export DEBIAN_FRONTEND=noninteractive
echo ">> 1/11 пакеты"; apt update && apt upgrade -y
apt install -y python3-venv python3-dev build-essential libpq-dev postgresql nginx ffmpeg git certbot python3-certbot-nginx ufw unzip
echo ">> 2/11 файрвол"; ufw allow OpenSSH; ufw allow 'Nginx Full'; ufw --force enable
echo ">> 3/11 swap"; if ! swapon --show | grep -q swapfile; then fallocate -l 2G /swapfile; chmod 600 /swapfile; mkswap /swapfile; swapon /swapfile; grep -q /swapfile /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab; fi
echo ">> 4/11 база"
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='plenka'" | grep -q 1 || sudo -u postgres psql -c "CREATE USER plenka WITH PASSWORD 'CHANGE_ME_DB_PASSWORD';"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='plenka'" | grep -q 1 || sudo -u postgres psql -c "CREATE DATABASE plenka OWNER plenka;"
echo ">> 5/11 .env"
cat > .env <<ENV
DEBUG=0
SECRET_KEY=CHANGE_ME_SECRET_KEY
ALLOWED_HOSTS=plenka-pics.ru,www.plenka-pics.ru,159.194.250.104
CSRF_TRUSTED_ORIGINS=https://plenka-pics.ru,https://www.plenka-pics.ru
POSTGRES_DB=plenka
POSTGRES_USER=plenka
POSTGRES_PASSWORD=CHANGE_ME_DB_PASSWORD
POSTGRES_HOST=localhost
TRUST_X_FORWARDED_FOR=1
MEDIA_X_ACCEL=1
MEDIA_ROOT=/srv/photohost/media
CACHE_DIR=/srv/photohost/cache
ADMIN_URL=panel-93fae927/
ENV
chown root:www-data .env; chmod 640 .env
echo ">> 6/11 venv + зависимости"; python3 -m venv venv; venv/bin/pip install --upgrade pip; venv/bin/pip install -r requirements.txt
echo ">> 7/11 миграции и статика"; venv/bin/python manage.py makemigrations photos; venv/bin/python manage.py migrate; venv/bin/python manage.py collectstatic --noinput
mkdir -p media tmp cache; chown -R www-data:www-data media tmp cache
echo ">> 8/11 админ Jusper"
DJANGO_SUPERUSER_USERNAME='Jusper' DJANGO_SUPERUSER_PASSWORD='CHANGE_ME_ADMIN_PASSWORD' DJANGO_SUPERUSER_EMAIL='' venv/bin/python manage.py createsuperuser --noinput || echo "(админ уже есть — пропускаю)"
echo ">> 9/11 служба"; cp deploy/plenka.service /etc/systemd/system/plenka.service; systemctl daemon-reload; systemctl enable --now plenka
echo ">> 10/11 nginx"; cp deploy/nginx.conf /etc/nginx/sites-available/plenka; ln -sf /etc/nginx/sites-available/plenka /etc/nginx/sites-enabled/plenka; rm -f /etc/nginx/sites-enabled/default; nginx -t && systemctl reload nginx
echo ">> 11/11 авто-очистка (cron)"; ( crontab -u www-data -l 2>/dev/null; echo '15 4 * * * cd /srv/photohost && venv/bin/python manage.py cleanup_posts && venv/bin/python manage.py clearsessions' ) | awk '!seen[$0]++' | crontab -u www-data -
systemctl --no-pager status plenka | head -4
echo
echo "================  ГОТОВО  ================"
echo "Дальше: направь домен на сервер (A-записи @ и www -> 159.194.250.104),"
echo "затем:   certbot --nginx -d plenka-pics.ru -d www.plenka-pics.ru"
echo "После сертификата открывай https://plenka-pics.ru"
