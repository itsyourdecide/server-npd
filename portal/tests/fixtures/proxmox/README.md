# Proxmox API fixtures

Статус: sanitized development fixtures
Дата источника: 2026-09-21
Источник: Proxmox VE `9.2.3`, `pve-docs 9.2.2`, cluster `npd`

Файлы сохраняют HTTP envelope Proxmox API (`{"data": ...}`) и реальные
названия полей, но не являются полным снимком кластера. Из них удалены token,
certificate fingerprints, MAC, UUID, внутренние IP и изменяющиеся показатели
нагрузки.

Fixtures предназначены для офлайн-разработки и тестирования parsing в
`ProxmoxClient`/`HttpProxmoxAdapter`. Их нельзя использовать как источник
текущей ёмкости или действующей конфигурации кластера.

Controlled clone template `9000` выполнен реальным ограниченным token.
Добавлены обезличенные ответы принятия clone/resize, running/succeeded task и
реальных ошибок ACL/delete. Значения UPID, PID, времени, MAC, UUID, IP и
пользовательского SSH key заменены безопасными примерами.

Успешная PVE task имеет `status="stopped"` и `exitstatus="OK"`. Значение
`status="stopped"` само по себе не означает успех: при ошибке `exitstatus`
содержит текст причины.

При delete проверенный вариант — `purge=1`. Fixture
`delete-unreferenced-failed.json` фиксирует, почему нельзя считать принятый
UPID успешной операцией до проверки конечного `exitstatus`.
