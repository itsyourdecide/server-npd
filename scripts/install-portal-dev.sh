#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "Run this script with sudo." >&2
    exit 1
fi

repo_root=/home/dev01/server-npd
portal_root=${repo_root}/portal
static_root=/var/lib/npd-portal/static

test -x "${portal_root}/.venv/bin/gunicorn"
test -f "${repo_root}/infra/systemd/portal-dev01/npd-portal.service"
test -f "${repo_root}/infra/nginx/portal-dev01/npd-portal.conf"

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install --yes nginx

install -D -m 0644 \
    "${repo_root}/infra/systemd/portal-dev01/npd-portal.service" \
    /etc/systemd/system/npd-portal.service
install -D -m 0644 \
    "${repo_root}/infra/nginx/portal-dev01/npd-portal.conf" \
    /etc/nginx/sites-available/npd-portal
ln -sfn /etc/nginx/sites-available/npd-portal \
    /etc/nginx/sites-enabled/npd-portal

install -d -o dev01 -g www-data -m 0755 "${static_root}"
runuser -u dev01 -- env \
    DJANGO_SETTINGS_MODULE=config.settings.development \
    DJANGO_STATIC_ROOT="${static_root}" \
    "${portal_root}/.venv/bin/python" \
    "${portal_root}/manage.py" collectstatic --noinput
chown -R dev01:www-data "${static_root}"
find "${static_root}" -type d -exec chmod 0755 {} +
find "${static_root}" -type f -exec chmod 0644 {} +

nginx -t
systemctl daemon-reload
systemctl enable --now npd-portal.service
systemctl enable --now nginx.service
systemctl reload nginx.service
