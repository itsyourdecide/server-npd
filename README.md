# server-npd — документация вычислительного кластера

Репозиторий содержит документацию, автоматизацию и проверяемые артефакты
кластера кафедры: Proxmox, HTCondor, PXE, сеть, хранилище, мониторинг и
пользовательский доступ.

## Начать здесь

1. [Текущее состояние](docs/current-state.md) — что было подтверждено, когда и
   какие проблемы известны.
2. [Открытые задачи](docs/project/open-issues.md) — что нужно сделать дальше.
3. [Roadmap](docs/project/roadmap.md) — порядок развития инфраструктуры.
4. [Правила документации](docs/documentation-guide.md) — куда и как вносить
   изменения, чтобы не создавать новые источники истины.
5. [План реорганизации](docs/documentation-reorganization-plan.md) — принятая
   структура и ход миграции старых документов.

## Быстрые операционные входы

- [Ansible](ansible/README.md) — настройка AlmaLinux, HTCondor, CVMFS,
  monitoring и NFS-клиентов.
- [Обзор архитектуры](docs/architecture/overview.md).
- [Адреса и VLAN](docs/network/addressing.md) и
  [топология сети](docs/network/topology.md).
- [Реестр оборудования](docs/inventory/hardware.md) и
  [реестр сервисов](docs/inventory/services.md).
- [История операций](docs/history/README.md).
- [Проверка здоровья кластера](docs/runbooks/cluster-health.md).
- [Ввод нового узла](docs/runbooks/provision-node.md) и
  [безопасная PXE-переустановка](docs/runbooks/pxe-reinstall.md).
- [Доступ пользователей](docs/services/user-access.md) — административная
  выдача SSH и HTCondor-доступа.
- [Выдача доступа пользователю](docs/runbooks/provision-user.md).
- [Краткая инструкция пользователю](docs/users/quickstart.md).
- [Monitoring](docs/services/monitoring.md).
- [Storage policy](docs/services/storage.md).
- `scripts/cluster-health.sh` — общая проверка кластера.
- `scripts/monitoring-health.sh` — проверка Prometheus targets.
- `scripts/user-access-health.sh` — проверка пользовательского SSH-пути.
- `python3 scripts/check-docs.py` — проверка структуры документации и ссылок.

## Статус реорганизации

Базовый объём этапов 1–6 выполнен 2026-09-05: созданы current state, backlog,
roadmap, ADR, сервисные документы и основные runbook'и. Журнал разделён по
месяцам, старые планы архивированы, конфигурации и evidence разнесены, а
проверка документации включена в CI. До закрытия оставшихся пунктов `DOC-001`
при расхождении следует доверять
[текущему состоянию](docs/current-state.md), если у факта указана дата проверки.

Историческая запись не доказывает, что компонент работает сегодня. Слова
«текущий» и «работает» без даты проверки не считаются подтверждением.

## Содержимое репозитория

- `ansible/` — воспроизводимая конфигурация AlmaLinux-узлов.
- `scripts/` — операционные проверки и helper-скрипты.
- `docs/` — активная документация и план её миграции.
- [`infra/`](infra/README.md) — действующие конфигурации вне Ansible.
- [`evidence/`](evidence/README.md) — датированные снимки и результаты проверок.
- `work/` — переходная заглушка; новые файлы туда не добавляются.
- `archive/` — исторические и неактуальные документы.

`cluster_shopping_list.md` является отдельным неотслеживаемым черновиком и не
включён в активные источники истины до его явного принятия.
