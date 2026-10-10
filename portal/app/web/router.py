from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compute.models import ComputePlan, UserQuota
from app.compute.services import get_user_compute_usage
from app.db.session import get_db
from app.identity.csrf import make_csrf_token, verify_csrf
from app.identity.dependencies import get_current_user
from app.operations.models import Operation
from app.ssh_keys.models import SshPublicKey
from app.users.models import User
from app.virtual_machines.models import VirtualMachine
from app.virtual_machines.schemas import VirtualMachineCreate
from app.virtual_machines.services import create_vm, enqueue_vm_operation

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[2] / "templates")


@router.get("/", response_class=HTMLResponse, name="home")
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={"authenticated": False},
    )


@router.get("/dashboard", response_class=HTMLResponse, name="dashboard")
async def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    csrf_token = make_csrf_token(request.cookies["npd_session"])
    quota = await db.get(UserQuota, user.id)
    plan = await db.get(ComputePlan, quota.compute_plan_id) if quota else None
    usage = await get_user_compute_usage(db, user.id) if plan else None

    vms = (await db.scalars(
        select(VirtualMachine)
        .where(VirtualMachine.owner_user_id == user.id)
        .order_by(VirtualMachine.created_at.desc())
    )).all()

    ssh_keys = (await db.scalars(
        select(SshPublicKey)
        .where(SshPublicKey.owner_user_id == user.id)
        .order_by(SshPublicKey.created_at.desc())
    )).all()

    operations = (await db.scalars(
        select(Operation)
        .join(VirtualMachine, Operation.virtual_machine_id == VirtualMachine.id)
        .where(VirtualMachine.owner_user_id == user.id)
        .order_by(Operation.created_at.desc())
        .limit(10)
    )).all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "authenticated": True,
            "user_id": user.id,
            "quota": quota,
            "plan": plan,
            "usage": usage,
            "vms": vms,
            "ssh_keys": ssh_keys,
            "operations": operations,
            "csrf_token": csrf_token,
            "create_vm_idempotency_key": str(uuid4()),
            "vm_start_idempotency_keys": {
                vm.id: str(uuid4()) for vm in vms if vm.status == "stopped"
            },
        },
    )


@router.post(
    "/dashboard/vms",
    dependencies=[Depends(verify_csrf)],
)
async def dashboard_vms(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> RedirectResponse:

    form = await request.form()

    try:
        request_model = VirtualMachineCreate.model_validate({
            "requested_vcpus": form.get("requested_vcpus"),
            "requested_memory_mb": form.get("requested_memory_mb"),
            "requested_storage_gb": form.get("requested_storage_gb"),
            "image_id": form.get("image_id"),
            "ssh_public_key_id": form.get("ssh_public_key_id"),
        })
        idempotency_key = UUID(str(form.get("idempotency_key")))
    except (ValidationError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid VM form") from exc

    try:
        await create_vm(
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

    return RedirectResponse(url="/dashboard#vms", status_code=303)


@router.post(
    "/dashboard/vms/{vm_id}/start",
    dependencies=[Depends(verify_csrf)],
)
async def vm_start(
    vm_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    form = await request.form()
    try:
        idempotency_key = str(UUID(str(form.get("idempotency_key"))))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid idempotency key") from exc

    try:
        await enqueue_vm_operation(
            db=db,
            user_id=user.id,
            vm_id=vm_id,
            operation_type="vm.start",
            idempotency_key=idempotency_key,
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

    return RedirectResponse(url="/dashboard#vms", status_code=303)
