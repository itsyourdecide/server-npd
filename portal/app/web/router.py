from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compute.models import ComputePlan, UserQuota
from app.compute.services import get_user_compute_usage
from app.db.session import get_db
from app.identity.csrf import make_csrf_token
from app.identity.dependencies import get_current_user
from app.operations.models import Operation
from app.ssh_keys.models import SshPublicKey
from app.users.models import User
from app.virtual_machines.models import VirtualMachine

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
        },
    )
