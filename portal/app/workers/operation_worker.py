import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select

from app.db.models import Operation
from app.db.session import SessionLocal
from app.operations.services import (
    process_create_vm_operation,
    finish_create_vm_dispatch,
    prepare_create_vm_dispatch,
    reconcile_create_vm_operation,
    process_delete_vm_operation,
    process_power_off_vm_operation,
    process_reboot_vm_operation,
    process_start_vm_operation,
    finish_start_vm_dispatch,
    finish_lifecycle_dispatch,
    prepare_start_vm_dispatch,
    prepare_lifecycle_dispatch,
    reconcile_start_vm_operation,
    reconcile_lifecycle_operation,
)
from app.proxmox.contracts import ProxmoxAdapter
from app.virtual_machines.models import VirtualMachine
from app.workers.adapter import create_worker_adapter

logger = logging.getLogger(__name__)

# Должно быть больше таймаута HTTP-клиента Proxmox: пока первый вызов ещё
# выполняется, другой воркер не должен принимать его за оборванный.
DISPATCH_GRACE = timedelta(minutes=5)
RECONCILE_DELAY = timedelta(seconds=10)


async def run_once(
    adapter: ProxmoxAdapter,
) -> bool:
    start_dispatch = None
    lifecycle_dispatch = None
    create_dispatch = None
    now = datetime.now(UTC)

    async with SessionLocal() as db, db.begin():
        statement = (
            select(Operation)
            .where(
                Operation.operation_type.in_((
                    "vm.create", "vm.start", "vm.shutdown",
                    "vm.stop", "vm.reboot", "vm.delete",
                )),
                Operation.status.in_(["pending", "processing"]),
                or_(
                    Operation.status == "pending",
                    and_(
                        Operation.phase.like("dispatch%"),
                        Operation.updated_at <= now - DISPATCH_GRACE,
                    ),
                    and_(
                        Operation.phase.like("reconcile%"),
                        Operation.updated_at <= now - RECONCILE_DELAY,
                    ),
                    and_(
                        Operation.phase.like("poll_backoff%"),
                        Operation.updated_at <= now - RECONCILE_DELAY,
                    ),
                    and_(
                        Operation.provider_task_id.is_not(None),
                        or_(
                            Operation.phase.is_(None),
                            ~Operation.phase.like("poll_backoff%"),
                        ),
                    ),
                ),
            )
            .order_by(Operation.updated_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )

        operation = await db.scalar(statement)

        if operation is None:
            return False

        logger.info(
        "operation_processing id=%s type=%s status=%s attempts=%s",
        operation.id,
        operation.operation_type,
        operation.status,
        operation.attempts,
        )

        if operation.operation_type == "vm.create":
            if operation.status == "pending":
                if operation.phase == "clone":
                    vm = await db.get(VirtualMachine, operation.virtual_machine_id)
                    if vm is None:
                        raise RuntimeError("virtual machine is missing")

                    if vm.provider_node is None and vm.provider_vmid is None:
                        # Выбор размещения не изменяет VM у провайдера.
                        await process_create_vm_operation(db, operation, adapter)
                    else:
                        phase = operation.phase
                        request, target = await prepare_create_vm_dispatch(db, operation)
                        create_dispatch = operation.id, operation.virtual_machine_id, phase, request, target
                elif operation.phase in {"configure", "resize", "start"}:
                    phase = operation.phase
                    request, target = await prepare_create_vm_dispatch(db, operation)
                    create_dispatch = operation.id, operation.virtual_machine_id, phase, request, target
                else:
                    raise RuntimeError(f"unsupported create phase: {operation.phase}")

            elif operation.provider_task_id is not None:
                if (operation.phase or "").startswith("poll_backoff_create_"):
                    operation.phase = operation.phase.removeprefix("poll_backoff_create_")
                try:
                    await process_create_vm_operation(db, operation, adapter)
                except Exception:
                    logger.exception("create_task_poll_failed id=%s", operation.id)
                    operation.phase = f"poll_backoff_create_{operation.phase}"
                    operation.last_error_code = "provider_status_unavailable"
                    operation.updated_at = datetime.now(UTC)

            elif (operation.phase or "").startswith(("dispatch_create_", "reconcile_create_")):
                try:
                    await reconcile_create_vm_operation(db, operation, adapter)
                except Exception:
                    logger.exception("create_reconciliation_failed id=%s", operation.id)
                    operation.phase = operation.phase.replace("dispatch_", "reconcile_", 1)
                    operation.last_error_code = "provider_status_unavailable"
                    operation.updated_at = datetime.now(UTC)

            else:
                raise RuntimeError(f"unsupported create phase: {operation.phase}")
        elif operation.operation_type == "vm.start":
            if operation.status == "pending":
                target = await prepare_start_vm_dispatch(db, operation)
                start_dispatch = (operation.id, operation.virtual_machine_id, target)

            elif operation.provider_task_id is not None:
                try:
                    await process_start_vm_operation(db, operation, adapter)
                except Exception:
                    logger.exception("start_task_poll_failed id=%s", operation.id)
                    operation.phase = "poll_backoff"
                    operation.last_error_code = "provider_status_unavailable"
                    operation.updated_at = datetime.now(UTC)

            elif operation.phase in {"dispatching", "reconcile"}:
                try:
                    await reconcile_start_vm_operation(db, operation, adapter)
                except Exception:
                    logger.exception("start_reconciliation_failed id=%s", operation.id)
                    operation.phase = "reconcile"
                    operation.last_error_code = "provider_status_unavailable"
                    operation.updated_at = datetime.now(UTC)

            else:
                raise RuntimeError(f"unsupported VM start phase: {operation.phase}")
        elif operation.operation_type in {"vm.shutdown", "vm.stop", "vm.reboot", "vm.delete"}:
            if operation.status == "pending":
                command, target = await prepare_lifecycle_dispatch(db, operation)
                lifecycle_dispatch = (
                    operation.id, operation.virtual_machine_id, command, target,
                )

            elif operation.provider_task_id is not None:
                if operation.operation_type == "vm.reboot" and (operation.phase or "").startswith("poll_backoff_"):
                    operation.phase = operation.phase.removeprefix("poll_backoff_")

                try:
                    if operation.operation_type in {"vm.shutdown", "vm.stop"}:
                        await process_power_off_vm_operation(db, operation, adapter)
                    elif operation.operation_type == "vm.reboot":
                        await process_reboot_vm_operation(db, operation, adapter)
                    else:
                        await process_delete_vm_operation(db, operation, adapter)
                except Exception:
                    logger.exception("lifecycle_task_poll_failed id=%s", operation.id)
                    operation.phase = (
                        f"poll_backoff_{operation.phase}"
                        if operation.operation_type == "vm.reboot"
                        else "poll_backoff"
                    )
                    operation.last_error_code = "provider_status_unavailable"
                    operation.updated_at = datetime.now(UTC)

            elif (operation.phase or "").startswith(("dispatch_", "reconcile_")):
                try:
                    await reconcile_lifecycle_operation(db, operation, adapter)
                except Exception:
                    logger.exception("lifecycle_reconciliation_failed id=%s", operation.id)
                    operation.phase = operation.phase.replace("dispatch_", "reconcile_", 1)
                    operation.last_error_code = "provider_status_unavailable"
                    operation.updated_at = datetime.now(UTC)

            else:
                raise RuntimeError(f"unsupported lifecycle phase: {operation.phase}")
        else:
            raise RuntimeError(
                f"unsupported operation type: {operation.operation_type}"
            )

        logger.info(
            "operation_processed id=%s status=%s provider_task_id=%s",
            operation.id,
            operation.status,
            operation.provider_task_id,
        )

    if create_dispatch is not None:
        operation_id, vm_id, phase, request, target = create_dispatch

        try:
            # Маркер уже сохранён, транзакция закрыта до сетевого вызова.
            if phase == "clone":
                result = await adapter.clone_vm(request, node=target.node, vmid=target.vmid)
            elif phase == "configure":
                result = await adapter.configure_vm(request, node=target.node, vmid=target.vmid)
            elif phase == "resize":
                result = await adapter.resize_vm_disk(request, node=target.node, vmid=target.vmid)
            elif phase == "start":
                result = await adapter.start_vm(vm_id, node=target.node, vmid=target.vmid)
            else:
                raise RuntimeError(f"unsupported create dispatch phase: {phase}")
        except Exception:
            logger.exception("create_submit_outcome_unknown id=%s phase=%s", operation_id, phase)
            try:
                async with SessionLocal() as db, db.begin():
                    operation = await db.get(Operation, operation_id, with_for_update=True)
                    if operation is None:
                        raise RuntimeError("VM create operation disappeared")
                    if operation.status != "processing" or operation.phase != f"dispatch_create_{phase}":
                        raise RuntimeError("VM create operation changed during dispatch")
                    operation.phase = f"reconcile_create_{phase}"
                    operation.last_error_code = "provider_submit_unknown"
                    operation.updated_at = datetime.now(UTC)
            except Exception:
                # Сохранённый dispatch_create_* тоже не позволит повторить команду.
                logger.exception("create_unknown_state_store_failed id=%s", operation_id)
            return True

        try:
            async with SessionLocal() as db, db.begin():
                operation = await db.get(Operation, operation_id, with_for_update=True)
                if operation is None:
                    raise RuntimeError("VM create operation disappeared")
                await finish_create_vm_dispatch(db, operation, phase, result)
        except Exception:
            # Результат мог быть принят провайдером, но не сохранён в БД.
            logger.exception("create_result_store_failed id=%s", operation_id)

    if start_dispatch is not None:
        operation_id, vm_id, target = start_dispatch

        # Здесь уже нет открытой транзакции или блокировки строки БД.
        try:
            task = await adapter.start_vm(
                vm_id,
                node=target.node,
                vmid=target.vmid,
            )
        except Exception:
            logger.exception("start_submit_outcome_unknown id=%s", operation_id)
            try:
                async with SessionLocal() as db, db.begin():
                    operation = await db.get(Operation, operation_id, with_for_update=True)
                    if operation is None:
                        raise RuntimeError("VM start operation disappeared")
                    if operation.status != "processing" or operation.phase != "dispatching":
                        raise RuntimeError("VM start operation changed during dispatch")
                    operation.phase = "reconcile"
                    operation.last_error_code = "provider_submit_unknown"
                    operation.updated_at = datetime.now(UTC)
            except Exception:
                # Маркер dispatching уже сохранён; после паузы его сверят с Proxmox.
                logger.exception("start_unknown_state_store_failed id=%s", operation_id)
            return True

        try:
            async with SessionLocal() as db, db.begin():
                operation = await db.get(Operation, operation_id, with_for_update=True)
                if operation is None:
                    raise RuntimeError("VM start operation disappeared")
                await finish_start_vm_dispatch(db, operation, task)
        except Exception:
            # Если UPID не удалось записать, не отправляем команду ещё раз.
            logger.exception("start_result_store_failed id=%s", operation_id)

    if lifecycle_dispatch is not None:
        operation_id, vm_id, command, target = lifecycle_dispatch

        # Для всех команд VM вызов провайдера идёт после коммита маркера.
        try:
            if command == "shutdown":
                result = await adapter.shutdown_vm(vm_id, node=target.node, vmid=target.vmid)
            elif command == "stop":
                result = await adapter.stop_vm(vm_id, node=target.node, vmid=target.vmid)
            elif command == "start":
                result = await adapter.start_vm(vm_id, node=target.node, vmid=target.vmid)
            elif command == "delete":
                result = await adapter.delete_vm(vm_id, node=target.node, vmid=target.vmid)
            else:
                raise RuntimeError(f"unsupported lifecycle command: {command}")
        except Exception:
            logger.exception("lifecycle_submit_outcome_unknown id=%s", operation_id)
            try:
                async with SessionLocal() as db, db.begin():
                    operation = await db.get(Operation, operation_id, with_for_update=True)
                    if operation is None or not operation.phase.startswith("dispatch_"):
                        raise RuntimeError("lifecycle operation changed during dispatch")
                    operation.phase = operation.phase.replace("dispatch_", "reconcile_", 1)
                    operation.last_error_code = "provider_submit_unknown"
                    operation.updated_at = datetime.now(UTC)
            except Exception:
                logger.exception("lifecycle_unknown_state_store_failed id=%s", operation_id)
            return True

        try:
            async with SessionLocal() as db, db.begin():
                operation = await db.get(Operation, operation_id, with_for_update=True)
                if operation is None:
                    raise RuntimeError("lifecycle operation disappeared")
                await finish_lifecycle_dispatch(db, operation, result)
        except Exception:
            logger.exception("lifecycle_result_store_failed id=%s", operation_id)

    return True


async def run_worker(
    adapter: ProxmoxAdapter,
) -> None:
    while True:
        try:
            processed = await run_once(adapter)
        except Exception:
            # Транзакция откатится, а сохранённую операцию подберём снова.
            logger.exception("operation_worker_iteration_failed")
            await asyncio.sleep(2)
            continue

        if processed:
            await asyncio.sleep(1)
        else:
            await asyncio.sleep(2)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    async with create_worker_adapter() as adapter:
        logger.info(
            "operation_worker_started adapter=%s",
            type(adapter).__name__,
        )

        await run_worker(adapter)


if __name__ == "__main__":
    asyncio.run(main())
