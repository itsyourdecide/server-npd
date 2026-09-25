from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.compute.models import ComputePlan, UserQuota
from app.compute.services import get_user_compute_usage
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

    usage = await get_user_compute_usage(db, user.id)

    remaining_vms = cp.max_vms - usage["used_vms"]
    remaining_vcpus = cp.max_total_vcpus - usage["used_vcpus"]
    remaining_memory_mb = cp.max_total_memory_mb - usage["used_memory_mb"]
    remaining_storage_gb = cp.max_total_storage_gb - usage["used_storage_gb"]
    remaining_shared_storage_gb = cp.max_shared_storage_gb - 0

    return {
        "status": uq.status,
        "plan": cp.code,
        "limits": {
            "vms": cp.max_vms,
            "vcpus": cp.max_total_vcpus,
            "memory_mb": cp.max_total_memory_mb,
            "storage_gb": cp.max_total_storage_gb,
            "shared_storage_gb": cp.max_shared_storage_gb
        },
        "usage": {
            "vms": usage["used_vms"],
            "vcpus": usage["used_vcpus"],
            "memory_mb": usage["used_memory_mb"],
            "storage_gb": usage["used_storage_gb"],
            "shared_storage_gb": 0,
        },
        "remaining": {
            "vms": remaining_vms,
            "vcpus": remaining_vcpus,
            "memory_mb": remaining_memory_mb,
            "storage_gb": remaining_storage_gb,
            "shared_storage_gb": remaining_shared_storage_gb
        },

    }

