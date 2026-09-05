# ADR-0002: HTCondor как основной scheduler

Статус: accepted
Дата решения: 2026-08-06
Последняя редакция: 2026-09-05
Источник истины для: выбора scheduler для основного compute pool

## Контекст

Основная ожидаемая нагрузка — множество независимых Geant4, ROOT и Monte Carlo
jobs. ASUS используются как bare-metal execute-ноды, а Supermicro могут позднее
предоставлять execute VM. Для HEP-workflows важны file transfer, retry,
fair-share и CVMFS.

Ранние архитектурные документы предполагали Slurm как основной scheduler, но
это решение было пересмотрено до развёртывания production compute pool.

## Рассмотренные варианты

### Slurm как единый scheduler

Подходит для tightly-coupled MPI/HPC и InfiniBand, но хуже отражает основной
профиль из большого числа независимых HTC jobs.

### HTCondor как основной scheduler

Соответствует HTC/HEP-нагрузке, поддерживает гетерогенные execute-ноды и хорошо
сочетается с CVMFS.

### Два scheduler сразу

Добавляет эксплуатационную сложность до появления реальной MPI-нагрузки.

## Решение

Использовать HTCondor как основной scheduler.

- `condor01` совмещает central manager и submit/access point на первом этапе.
- ASUS являются bare-metal execute nodes.
- Supermicro execute workload запускается только внутри VM.
- CVMFS предоставляет scientific software.
- Одинаковые numeric UID поддерживаются на submit и execute nodes.
- Slurm не разворачивается заранее и остаётся отдельным будущим MPI/HPC-слоем.

## Последствия

Плюсы:

- архитектура соответствует текущим HEP-задачам;
- отказ execute-ноды уменьшает capacity, но не ломает инфраструктуру;
- compute fleet можно расширять постепенно;
- пользователи работают через submit host, а не входят на workers.

Ограничения:

- многонодовые MPI-задачи требуют отдельного решения;
- identity, shared data и checkpoint policy должны быть согласованы;
- автоматический power management ASUS ещё не реализован;
- центральный manager/submit пока совмещён в одной VM.

## Условия пересмотра

- появляется подтверждённый класс многонодовых MPI-задач;
- InfiniBand topology проверена и требуется пользователям;
- HTCondor не закрывает scheduling/fair-share требования;
- появляется необходимость интеграции с внешним grid/DIRAC.

При выполнении условий создаётся новый ADR. Этот документ не переписывается так,
чтобы скрыть предыдущее решение.
