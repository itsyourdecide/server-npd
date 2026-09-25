from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.identity.dependencies import get_current_user
from app.ssh_keys.exceptions import (
    InvalidSshPublicKeyError,
    SshPublicKeyConflictError,
)
from app.ssh_keys.models import SshPublicKey
from app.ssh_keys.schemas import SshPublicKeyCreate, SshPublicKeyRead
from app.ssh_keys.services import import_ssh_public_key
from app.users.models import User
from app.ssh_keys.services import generate_ssh_key_pair
from app.ssh_keys.schemas import GeneratedSshKeyPairRead, SshKeyPairGenerate

router = APIRouter(
    prefix="/compute/ssh-keys",
    tags=["ssh-keys"],
)


@router.post(
    "/import",
    response_model=SshPublicKeyRead,
    status_code=status.HTTP_201_CREATED,
)
async def import_ssh_key(
    request_model: SshPublicKeyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):

    try:
        ssh_key = await import_ssh_public_key(
            db,
            user_id=user.id,
            request_model=request_model,
        )
        await db.commit()

    except InvalidSshPublicKeyError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except SshPublicKeyConflictError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except Exception:
        await db.rollback()
        raise

    await db.refresh(ssh_key)
    return ssh_key


@router.get(
    "",
    response_model=list[SshPublicKeyRead],
)
async def get_list_keys(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    statement = select(SshPublicKey).where(
        SshPublicKey.owner_user_id == user.id,
        ).order_by(SshPublicKey.created_at.desc())
    
    result = await db.scalars(statement)

    return result.all()


@router.post(
    "/generate",
    response_model=GeneratedSshKeyPairRead,
    status_code=status.HTTP_201_CREATED,
)
async def generate_ssh_key_pair_endpoint(
    request_model: SshKeyPairGenerate,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):

    try:
        generated = await generate_ssh_key_pair(
            db,
            user_id=user.id,
            request_model=request_model,
        )
        await db.commit()

    except SshPublicKeyConflictError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    except Exception:
        await db.rollback()
        raise

    await db.refresh(generated.ssh_key)
    
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"

    return {
        "key": generated.ssh_key,
        "private_key": generated.private_key,
    }