from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.identity.dependencies import get_current_user
from app.users.models import User
from app.virtual_machines.models import VirtualMachine
from app.virtual_machines.schemas import VirtualMachineCreate, VirtualMachineRead
from app.virtual_machines.services import create_vm

router = APIRouter(prefix="/compute/vms")


@router.get("", response_model=list[VirtualMachineRead])
async def my_vms(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
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
):
    try:
        vm = await create_vm(
            db,
            user_id=user.id,
            request_model=request_model,
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
