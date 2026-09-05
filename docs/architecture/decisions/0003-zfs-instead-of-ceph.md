# ADR-0003: ZFS replication вместо Ceph на текущем этапе

- Статус: accepted
- Дата решения: 2026-07-02
- Последняя редакция: 2026-09-05
Источник истины для: выбора storage-механизма для VM и условий возврата к Ceph

## Контекст

Для перезапуска VM после отказа узла её диск должен быть доступен на другом
Proxmox host. Первоначальная архитектура предполагала Ceph RBD и CephFS на
дисках из JBOD-полок.

На момент решения не было подтверждено достаточно независимых storage failure
domains и выделенной сети для Ceph. Бюджет не покрывал полноценную 10GbE-схему,
а recovery большого HDD через 1GbE создавал бы длительную нагрузку и риск для
остальной инфраструктуры.

Позднее в Force10 обнаружились два 10GbE SFP+ порта. Это делает отдельные тесты
возможными, но само по себе не создаёт production Ceph network для трёх и более
storage hosts.

## Рассмотренные варианты

### Ceph RBD/CephFS

Даёт shared storage и распределение реплик по failure domains, но требует
достаточной сети, нескольких storage hosts, burn-in дисков и более сложной
эксплуатации.

### Локальные ZFS-диски без репликации

Просты и быстры, но после отказа host другой узел не получает актуальный диск
критичной VM.

### Proxmox ZFS replication

Передаёт snapshots локального ZFS volume на другие PVE-узлы и не требует Ceph
control plane. Репликация асинхронна: возможен ненулевой RPO, а failover требует
актуальной реплики и корректной процедуры.

## Решение

На текущем этапе:

- диски VM размещаются на локальном ZFS;
- критичные VM реплицируются средствами Proxmox ZFS replication;
- общий файловый storage не пытаются изображать через ZFS replication;
- общий `/data` реализуется отдельно: pool `npddata` на `pve01`, NFS export
  `10.10.80.2:/data`;
- Ceph имеет статус deferred, а не rejected forever;
- ZFS replication и NFS не считаются backup.

## Последствия

Плюсы:

- можно использовать существующую 1GbE-сеть для небольшого объёма replication;
- меньше компонентов и проще диагностика;
- решение встроено в действующий Proxmox cluster;
- storage для VM отделён от общего HTCondor `/data`.

Ограничения:

- replication асинхронна и не даёт zero-RPO;
- replicated volume не является одновременно доступным shared disk;
- NFS на `pve01` имеет storage-head failure domain;
- automatic failover не считается готовым без fencing и испытанного runbook;
- удаление или повреждение может попасть в реплики, поэтому нужен backup.

## Условия возврата к Ceph

Ceph пересматривается только при выполнении одного или нескольких условий:

- есть выделенная сеть минимум 10GbE для достаточного числа Ceph hosts;
- есть не менее трёх проверенных независимых storage failure domains;
- диски прошли SMART/burn-in и enclosure/slot mapping;
- реальная нагрузка показывает недостаточность NFS/ZFS replication;
- конкретному сервису требуется shared storage или более строгий RPO;
- команда готова сопровождать recovery, capacity и failure procedures.

Перед включением Ceph требуется новый ADR с topology, сетью, capacity model,
failure tests, backup boundary и rollback plan.

## Связанные решения и состояние

- [Архитектура](../overview.md).
- [Текущее состояние](../../current-state.md).
- [Открытая задача STO-002](../../project/open-issues.md#sto-002--пересмотр-ceph).

Исходный документ `storage_decision_zfs_replication.md` перенесён в этот ADR и
переработан без изменения сути принятого решения.
