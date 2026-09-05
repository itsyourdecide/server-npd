# PXE/iPXE service

- Статус: current snapshot
- Последняя подтверждённая проверка: 2026-08-07
- Источник истины для: PXE flow, роли Nginx/TFTP и безопасной переустановки

## Placement

| Field | Value |
|---|---|
| Service | `pxe01.internal` |
| Placement | LXC 110 на `pve02` |
| Address | `10.10.80.10` |
| VLAN | 80 |
| Services | `tftpd-hpa`, Nginx, iPXE assets |

## Boot flow

```text
node firmware
  -> DHCP/Dnsmasq on fw01
  -> TFTP /srv/tftp/ipxe.efi
  -> embedded iPXE
  -> Nginx http://10.10.80.10/boot.ipxe
  -> MAC policy / menu / install-once flag
  -> kernel + initrd + Kickstart
  -> AlmaLinux package repository through Nginx cache
  -> firstboot
  -> Ansible roles
```

TFTP используется только для небольшого первого загрузчика. Большие файлы,
меню и Kickstart отдаёт Nginx из `/srv/pxe/http`.

## Nginx package cache

`/alma-cache/` проксирует `repo.almalinux.org` и хранит cache в
`/srv/pxe/cache/nginx/alma` с лимитом 40 GiB. Runtime DNS resolver указывает на
`10.10.80.1`, чтобы Nginx не падал при старте из-за слишком раннего разрешения
upstream hostname.

## Reinstall safety

Known ASUS node не переустанавливается только из-за PXE boot. Destructive
профиль разрешается временным файлом:

```text
/srv/pxe/http/install-once/<lan-mac>.ipxe
```

Watcher обрабатывает только новые строки Nginx access log и перемещает флаг в
`used/` после первого успешного HTTP 200. Перед массовым запуском обязателен
dry-run по CSV inventory.

## Configuration source

Авторитетная repository copy находится в [`infra/pxe/`](../../infra/pxe/):

- `http/` — boot menu, profiles, Kickstart и firstboot;
- `nginx/` — Nginx site и cache path;
- `create-install-once*.sh` и `install-once-watcher.sh` — защита от случайной
  повторной установки.

Runtime copy на `pxe01` расположена в `/srv/pxe`; совпадение с репозиторием
нужно проверять после deployment.

## Verification

```bash
cd /root/server-npd
./scripts/cluster-health.sh --skip-storage
```

Проверка должна подтверждать `nginx`, `tftpd-hpa` и HTTP `boot.ipxe`. Реальная
destructive установка не входит в обычный health-check.

## Related

- [Current state](../current-state.md).
- [Addressing](../network/addressing.md).
- [Hardware inventory](../inventory/hardware.md).
