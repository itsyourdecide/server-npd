from dataclasses import dataclass, field
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ssh_keys.exceptions import (
    InvalidSshPublicKeyError,
    SshPublicKeyConflictError,
)
from app.ssh_keys.models import SshPublicKey
from app.ssh_keys.parsing import parse_ssh_public_key
from app.ssh_keys.schemas import SshKeyPairGenerate, SshPublicKeyCreate


async def import_ssh_public_key(
    db: AsyncSession,
    *,
    user_id: UUID,
    request_model: SshPublicKeyCreate,
) -> SshPublicKey:
    public_key = request_model.public_key
    name = request_model.name

    try:
        parsed_key = parse_ssh_public_key(public_key)
    except ValueError as exc:
        raise InvalidSshPublicKeyError(str(exc)) from exc

    key_type = parsed_key.key_type
    public_key = parsed_key.public_key
    fingerprint = parsed_key.fingerprint

    existing_name = await db.scalar(
        select(SshPublicKey).where(
            SshPublicKey.owner_user_id == user_id,
            SshPublicKey.name == name
        )
    )

    if existing_name is not None:
        raise SshPublicKeyConflictError("SSH key name already exists")

    existing_key = await db.scalar(
        select(SshPublicKey).where(
            SshPublicKey.fingerprint == fingerprint
        )
    )

    if existing_key is not None:
        raise SshPublicKeyConflictError("SSH public key already exists")

    pubkey = SshPublicKey(
        owner_user_id=user_id,
        name=name,
        key_type=key_type,
        public_key=public_key,
        fingerprint=fingerprint,
    )
    db.add(pubkey)
    await db.flush()

    return pubkey


@dataclass(frozen=True, slots=True)
class GeneratedSshKeyPair:
    ssh_key: SshPublicKey
    private_key: str = field(repr=False)


async def generate_ssh_key_pair(
    db: AsyncSession,
    *,
    user_id: UUID,
    request_model: SshKeyPairGenerate,
) -> GeneratedSshKeyPair:

    existing_name = await db.scalar(
        select(SshPublicKey).where(
            SshPublicKey.owner_user_id == user_id,
            SshPublicKey.name == request_model.name
        )
    )

    if existing_name is not None:
        raise SshPublicKeyConflictError("SSH key name already exists")

    private_key = ed25519.Ed25519PrivateKey.generate()

    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode("ascii")

    parsed_key = parse_ssh_public_key(public_key)

    private_key_text = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")

    pubkey = SshPublicKey(
        owner_user_id=user_id,
        name=request_model.name,
        key_type=parsed_key.key_type,
        public_key=parsed_key.public_key,
        fingerprint=parsed_key.fingerprint,
    )

    db.add(pubkey)
    await db.flush()

    return GeneratedSshKeyPair(
        ssh_key=pubkey,
        private_key=private_key_text,
    )