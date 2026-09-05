# Ввод AlmaLinux-узла в кластер

- Статус: current
- Последняя проверка процедуры: 2026-09-05
- Last tested: 2026-08-07
- Назначение: воспроизводимый ввод нового HTCondor-узла после установки ОС
- Источник истины для: последовательности PXE → inventory → Ansible → проверка

## Воздействие

Ansible изменяет конфигурацию выбранного узла. PXE-переустановка уничтожает
его локальную ОС и выполняется только по отдельному
[runbook](pxe-reinstall.md). Остальные узлы не должны входить в `--limit`.

## Предпосылки

- оборудование и MAC/IP внесены в [hardware inventory](../inventory/hardware.md)
  и [addressing](../network/addressing.md);
- порт свитча и VLAN подтверждены по фактической port map;
- для переустановки есть консоль/IPMI и резервный административный доступ;
- DNS-имя узла разрешается;
- SSH host key проверен после установки;
- локальный `ansible/inventory/group_vars/all/vault.yml` содержит требуемый
  `htcondor_pool_password` и не попадает в Git.

## Процедура

1. При необходимости установить базовую AlmaLinux через
   [PXE-процедуру](pxe-reinstall.md).
2. Добавить узел в правильную группу `ansible/inventory/hosts.yml`.
3. Проверить точную цель до применения конфигурации:

```bash
cd ansible
ansible-inventory --host <fqdn>
ansible <fqdn> -m ping
```

4. Применить базовую роль только к этому узлу:

```bash
ansible-playbook playbooks/base.yml --limit <fqdn>
```

5. Для HTCondor execute-узла применить роли по очереди:

```bash
ansible-playbook playbooks/cvmfs_client.yml --limit <fqdn>
ansible-playbook playbooks/storage_client.yml --limit <fqdn>
ansible-playbook playbooks/htcondor_execute.yml --limit <fqdn>
```

Storage role пропустить, если `/data` официально offline; это ограничение
зафиксировать в результате ввода.

## Проверка

```bash
ansible <fqdn> -m shell -a 'hostname -f; systemctl is-active condor; cvmfs_config probe sft.cern.ch'
ansible condor01.internal -m shell -a 'condor_status -af Name State Activity'
```

Затем запустить [общую проверку](cluster-health.md). Узел считается введённым,
когда его identity, сервисы и присутствие в `condor_status` подтверждены.

## Стоп и rollback

Остановиться при несовпадении MAC/IP/hostname, неожиданном составе `--limit`,
ошибке Vault, потере сети или наличии данных на целевом диске. Не продолжать
массовым запуском.

Rollback выполняется повторным применением предыдущей версии Ansible. Если
откат невозможен, исключить узел из HTCondor, пометить его unavailable в
inventory/current state и создать задачу в open issues.
