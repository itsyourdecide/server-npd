# Development deployment портала

- Статус: current
- Последняя проверка процедуры: 2026-09-10
- Last tested: 2026-09-10
- Назначение: запустить development-экземпляр портала через Gunicorn и Nginx
- Источник истины для: deployment portal на `portal-dev01`

Этот runbook поднимает текущий Django-портал на `portal-dev01` для внутренней
разработки. Это не production deployment: трафик использует HTTP, Google OIDC
ещё не включается, а Django загружает `config.settings.development`.

## Компоненты

- Nginx принимает HTTP на `10.10.40.107:80`;
- Gunicorn слушает только `127.0.0.1:8000`;
- systemd управляет процессом `npd-portal.service`;
- PostgreSQL остаётся локальным на `127.0.0.1:5432`;
- static files находятся в `/var/lib/npd-portal/static`.

## Установка

Из корня актуальной рабочей копии:

```bash
cd /home/dev01/server-npd
python3 -m venv portal/.venv
portal/.venv/bin/python -m pip install --editable portal
sudo ./scripts/install-portal-dev.sh
```

Скрипт устанавливает Nginx через APT, размещает version-controlled
конфигурации в `/etc`, собирает static files и включает оба systemd-сервиса.

## Проверка

```bash
systemctl status npd-portal nginx --no-pager
curl --fail http://127.0.0.1/health/live
curl --fail http://127.0.0.1/health/ready
```

В журнал Django/Gunicorn можно смотреть так:

```bash
journalctl -u npd-portal -f
```

## Обновление приложения

```bash
cd /home/dev01/server-npd
git pull --ff-only
portal/.venv/bin/python -m pip install --editable portal
portal/.venv/bin/python portal/manage.py migrate
sudo systemctl restart npd-portal
```

При изменении static files повторно запускается установочный скрипт.
