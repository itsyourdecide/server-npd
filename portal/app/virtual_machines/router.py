from typing import Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.identity.dependencies import get_current_user
from app.operations.models import Operation
from app.operations.schemas import OperationRead
from app.users.models import User
from app.virtual_machines.models import VirtualMachine
from app.virtual_machines.schemas import VirtualMachineCreate, VirtualMachineRead
from app.virtual_machines.services import create_vm, enqueue_vm_operation

router = APIRouter(prefix="/compute/vms")


@router.get("", response_model=list[VirtualMachineRead])
async def my_vms(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Sequence[VirtualMachine]:
    statement = (
    select(VirtualMachine)
        .where(VirtualMachine.owner_user_id == user.id)
        .order_by(VirtualMachine.created_at.desc())
    )
    vms = await db.scalars(statement)

    return vms.all()

@router.post(
    "",
    response_model=VirtualMachineRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_my_vm(
    request_model: VirtualMachineCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    idempotency_key: UUID = Header(alias="Idempotency-Key")
) -> VirtualMachine:
    try:
        vm = await create_vm(
            db,
            user_id=user.id,
            request_model=request_model,
            idempotency_key=str(idempotency_key),
        )
        await db.commit()

    except PermissionError as exc:
        await db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        await db.rollback()
        raise

    await db.refresh(vm)
    return vm

@router.post(
        "/{vm_id}/start",
        response_model=OperationRead,
        status_code=status.HTTP_202_ACCEPTED,)
async def start_vm(
    vm_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: UUID = Header(alias="Idempotency-Key")
) -> Operation:
    return await _enqueue_lifecycle_operation(
        db, current_user, vm_id, "vm.start", idempotency_key,
    )


async def _enqueue_lifecycle_operation(
    db: AsyncSession,
    current_user: User,
    vm_id: UUID,
    operation_type: str,
    idempotency_key: UUID,
) -> Operation:
    try:
        operation = await enqueue_vm_operation(
            db,
            user_id=current_user.id,
            vm_id=vm_id,
            operation_type=operation_type,
            idempotency_key=str(idempotency_key),
        )
        await db.commit()

    except LookupError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    except Exception:
        await db.rollback()
        raise

    await db.refresh(operation)
    return operation


@router.post(
    "/{vm_id}/shutdown",
    response_model=OperationRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def shutdown_vm(
    vm_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
) -> Operation:
    return await _enqueue_lifecycle_operation(
        db, current_user, vm_id, "vm.shutdown", idempotency_key,
    )


@router.post(
    "/{vm_id}/stop",
    response_model=OperationRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def stop_vm(
    vm_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
) -> Operation:
    return await _enqueue_lifecycle_operation(
        db, current_user, vm_id, "vm.stop", idempotency_key,
    )


@router.post(
    "/{vm_id}/reboot",
    response_model=OperationRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reboot_vm(
    vm_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
) -> Operation:
    return await _enqueue_lifecycle_operation(
        db, current_user, vm_id, "vm.reboot", idempotency_key,
    )


@router.post(
    "/{vm_id}/delete",
    response_model=OperationRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def delete_vm(
    vm_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
) -> Operation:
    return await _enqueue_lifecycle_operation(
        db, current_user, vm_id, "vm.delete", idempotency_key,
    )

@router.get(
    "/{vm_id}/operations/{operation_id}",
    response_model=OperationRead,
    status_code=status.HTTP_200_OK,
)
async def operation_status(
    vm_id: UUID,
    operation_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Operation:

    operation = await db.scalar(
        select(Operation)
        .join(VirtualMachine, Operation.virtual_machine_id == VirtualMachine.id)
        .where(
            VirtualMachine.id == vm_id,
            Operation.id == operation_id,
            VirtualMachine.owner_user_id == current_user.id
        )
    )

    if not operation:
        raise HTTPException(status_code=404, detail="Operation not found")

    return operation