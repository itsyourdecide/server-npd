import asyncio

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.ssh_keys.exceptions import SshPublicKeyConflictError
from app.ssh_keys.models import SshPublicKey
from app.ssh_keys.schemas import SshPublicKeyCreate
from app.ssh_keys.services import import_ssh_public_key

SSH_PUBLIC_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILXD5hvkNQhVB+lAbP50cAdixrOMIAMwW8O55MxYqqMn"
)


def _request(name: str, public_key: str = SSH_PUBLIC_KEY) -> SshPublicKeyCreate:
    return SshPublicKeyCreate(name=name, public_key=public_key)


@pytest.mark.asyncio
async def test_import_duplicate_name_conflicts(db, user) -> None:
    await import_ssh_public_key(db, user_id=user.id, request_model=_request("laptop"))

    with pytest.raises(SshPublicKeyConflictError, match="name already exists"):
        await import_ssh_public_key(
            db, user_id=user.id, request_model=_request("laptop")
        )


@pytest.mark.asyncio
async def test_import_duplicate_fingerprint_conflicts(db, user) -> None:
    await import_ssh_public_key(db, user_id=user.id, request_model=_request("first"))

    with pytest.raises(SshPublicKeyConflictError, match="already exists"):
        await import_ssh_public_key(
            db, user_id=user.id, request_model=_request("second")
        )


@pytest.mark.asyncio
async def test_concurrent_import_of_same_name_yields_single_key(db, user) -> None:
    # Двойной клик по «Импортировать»: оба pre-check'а не видят друг друга,
    # уникальный индекс (owner, name) решает спор, проигравший после
    # rollback видит строку победителя и получает конфликт.
    await db.commit()

    async def import_and_commit():
        async with SessionLocal() as session:
            key = await import_ssh_public_key(
                session, user_id=user.id, request_model=_request("laptop")
            )
            await session.commit()
            return key.id

    results = await asyncio.gather(
        import_and_commit(),
        import_and_commit(),
        return_exceptions=True,
    )

    errors = [r for r in results if isinstance(r, Exception)]
    winners = [r for r in results if not isinstance(r, Exception)]

    assert len(winners) == 1
    assert len(errors) == 1
    assert "name already exists" in str(errors[0])

    async with SessionLocal() as fresh:
        keys = list(await fresh.scalars(select(SshPublicKey)))
    assert len(keys) == 1


@pytest.mark.asyncio
async def test_concurrent_import_of_same_key_yields_fingerprint_conflict(db, user) -> None:
    # Разные имена, один публичный ключ: гонка упирается в глобальный
    # индекс fingerprint, проигравший получает конфликт по отпечатку.
    await db.commit()

    async def import_named(name: str):
        async with SessionLocal() as session:
            key = await import_ssh_public_key(
                session, user_id=user.id, request_model=_request(name)
            )
            await session.commit()
            return key.id

    results = await asyncio.gather(
        import_named("first"),
        import_named("second"),
        return_exceptions=True,
    )

    errors = [r for r in results if isinstance(r, Exception)]
    winners = [r for r in results if not isinstance(r, Exception)]

    assert len(winners) == 1
    assert len(errors) == 1
    assert "SSH public key already exists" in str(errors[0])

    async with SessionLocal() as fresh:
        keys = list(await fresh.scalars(select(SshPublicKey)))
    assert len(keys) == 1
