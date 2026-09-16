from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.compute.models import ComputePlan, UserQuota
from app.db.session import get_db
from app.identity.dependencies import get_current_user
from app.users.models import User

router = APIRouter(prefix="/compute")

@router.get("/quota")
async def get_quota(
    user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db),
):
    uq = await db.get(UserQuota, user.id)

    if uq is None:
        raise RuntimeError("user quota missing")
    
    cp = await db.get(ComputePlan, uq.compute_plan_id)

    if cp is None:
        raise RuntimeError("compute plan missing")

    return {
        "status": uq.status,
        "plan": cp.code,
        "max_vms": cp.max_vms,
        "max_running_vms": cp.max_running_vms,
        "max_total_vcpus": cp.max_total_vcpus,
        "max_total_memory_mb": cp.max_total_memory_mb,
        "max_total_storage_gb": cp.max_total_storage_gb,
        "max_shared_storage_gb": cp.max_shared_storage_gb,
    }

