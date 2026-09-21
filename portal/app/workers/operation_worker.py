import asyncio
import logging

from sqlalchemy import select

from app.db.models import Operation
from app.db.session import SessionLocal
from app.operations.services import process_create_vm_operation
from app.proxmox.contracts import ProxmoxAdapter
from app.proxmox.fake import FakeProxmoxAdapter

logger = logging.getLogger(__name__)


async def run_once(
    adapter: ProxmoxAdapter,
) -> bool:
    async with SessionLocal() as db, db.begin():
        statement = (
            select(Operation)
            .where(
                Operation.operation_type == "vm.create",
                Operation.status.in_(["pending", "processing"]),
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

        await process_create_vm_operation(
            db=db,
            operation=operation,
            adapter=adapter,
        )

        logger.info(
            "operation_processed id=%s status=%s provider_task_id=%s",
            operation.id,
            operation.status,
            operation.provider_task_id,
        )
        
    return True


async def run_worker(
    adapter: ProxmoxAdapter,
) -> None:
    while True:
        processed = await run_once(adapter)

        if processed:
            await asyncio.sleep(1)
        else:
            await asyncio.sleep(2)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    adapter = FakeProxmoxAdapter()

    logger.info(
        "operation_worker_started adapter=%s",
        type(adapter).__name__,
    )

    await run_worker(adapter)


if __name__ == "__main__":
    asyncio.run(main())