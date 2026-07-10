# Runbook: ручная проверка failover для `fw01`

Дата: 2026-07-08
Статус: Вариант A выполнен успешно 2026-07-08, Вариант B не выполнен
Связанные документы: `cluster_operations_log.md`, `storage_decision_zfs_replication.md`

## Цель

Проверить, что `fw01` можно поднять на узле с ZFS-репликой, без включения автоматического HA/fencing.

Текущая исходная точка:

- `fw01` = VM `100`;
- рабочий узел сейчас `pve02`;
- реплики диска есть на `pve03` и `pve01`;
- VM config существует на `pve02`, на `pve03`/`pve01` сейчас есть только replicated ZFS volume;
- HA-ресурсы не включены.

## Вариант A — мягкая planned migration

Это менее показательный, но самый безопасный первый тест. Он проверяет, что `fw01` может переехать с `pve02` на `pve03`, пока исходный узел жив.

Предварительные проверки:

```bash
pvecm status
ssh root@10.10.10.12 'pvesr status --guest 100'
ssh root@10.10.10.12 'qm status 100'
ssh root@10.10.10.13 'zfs list | grep vm-100-disk-0'
```

Команда planned migration:

```bash
ssh root@10.10.10.12 'qm migrate 100 pve03 --online --targetstorage 1 --with-local-disks'
```

Нюанс, подтверждённый тестом 2026-07-08: без `--with-local-disks` Proxmox отказывается live-migrate attached local ZFS disk, даже если диск реплицирован.

Проверка после миграции:

```bash
ssh root@10.10.10.13 'qm status 100'
ping -c 3 10.10.10.1
ping -c 3 10.10.40.1
pvecm status
```

Откат тем же способом:

```bash
ssh root@10.10.10.13 'qm migrate 100 pve02 --online --targetstorage 1 --with-local-disks'
```

## Вариант B — контролируемый replica failover с коротким простоем

Это ближе к настоящему отказу, но всё равно контролируемо: исходный узел `pve02` жив, VM штатно выключается, затем VM config переносится на целевой узел с репликой и VM стартует там.

**Важно:** этот вариант временно остановит `fw01`, то есть маршрутизация между VLAN и интернет для внутренних VLAN может пропасть на время теста.

Предварительные проверки:

```bash
pvecm status
ssh root@10.10.10.12 'pvesr status --guest 100'
ssh root@10.10.10.12 'qm config 100'
ssh root@10.10.10.13 'test -e /etc/pve/nodes/pve03/qemu-server/100.conf; echo $?'
ssh root@10.10.10.13 'zfs list rpool/data/vm-100-disk-0'
```

Финальная синхронизация перед остановкой:

```bash
ssh root@10.10.10.12 'pvesr run --id 100-0 --verbose'
```

Остановить VM на исходном узле:

```bash
ssh root@10.10.10.12 'qm shutdown 100 --timeout 120'
ssh root@10.10.10.12 'qm status 100'
```

Если shutdown зависнет и пользователь согласует принудительную остановку:

```bash
ssh root@10.10.10.12 'qm stop 100'
```

Перенести VM config на целевой узел:

```bash
mv /etc/pve/nodes/pve02/qemu-server/100.conf /etc/pve/nodes/pve03/qemu-server/100.conf
```

Запустить `fw01` на `pve03`:

```bash
ssh root@10.10.10.13 'qm start 100'
ssh root@10.10.10.13 'qm status 100'
```

Проверки после старта:

```bash
pvecm status
ping -c 3 10.10.10.1
ping -c 3 10.10.30.1
ping -c 3 10.10.40.1
ping -c 3 10.10.80.1
```

Проверить внешнюю связность из тестового контейнера:

```bash
ssh root@10.10.10.12 'pct exec 101 -- ping -c 3 1.1.1.1'
```

## Возврат `fw01` на `pve02` после Варианта B

После запуска на `pve03` именно диск на `pve03` становится актуальной копией. Диск на `pve02` с этого момента считается stale, поэтому **нельзя** просто перенести VM config обратно на `pve02` и стартовать старый диск.

Безопасный возврат — миграцией с текущего владельца (`pve03`) обратно на `pve02`:

```bash
ssh root@10.10.10.13 'qm migrate 100 pve02 --online --targetstorage 1'
```

Если online migration не подходит, выполнить cold migration:

```bash
ssh root@10.10.10.13 'qm shutdown 100 --timeout 120'
ssh root@10.10.10.13 'qm migrate 100 pve02 --targetstorage 1'
```

Проверить, что VM снова принадлежит `pve02`:

```bash
ssh root@10.10.10.12 'qm status 100'
test -e /etc/pve/nodes/pve02/qemu-server/100.conf
test ! -e /etc/pve/nodes/pve03/qemu-server/100.conf
```

Принудительно обновить репликации:

```bash
ssh root@10.10.10.12 'pvesr run --id 100-0 --verbose'
ssh root@10.10.10.12 'pvesr run --id 100-1 --verbose'
ssh root@10.10.10.12 'pvesr status --guest 100'
```

## Стоп-критерии

Не начинать тест, если:

- `pvecm status` не показывает `Quorate: Yes`;
- `pvesr status --guest 100` показывает `FailCount > 0` или не `State OK`;
- реплика `rpool/data/vm-100-disk-0` отсутствует на целевом узле;
- нет локального/консольного fallback-доступа на случай, если `fw01` перестанет маршрутизировать VLAN.

Остановиться и не продолжать без отдельного решения, если:

- `qm shutdown 100` не завершился штатно;
- после переноса config Proxmox показывает lock/duplicate VMID;
- `fw01` стартовал, но не отвечает `10.10.10.1`;
- потерян доступ к Proxmox GUI/SSH через текущий маршрут.

## Рекомендация

Первым запускать Вариант A. Если он проходит чисто, отдельно согласовать окно на Вариант B: это уже настоящий короткий outage для `fw01`.
