from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compute.services import assign_starter_quota
from app.db.models import ExternalIdentity, User


async def get_or_create_user(
        db: AsyncSession,
        *,
        issuer: str,
        subject: str,
        email: str,
) -> User:
    """Return the Portal user for a verified external identity."""

    statement = select(ExternalIdentity).where(
    ExternalIdentity.issuer == issuer,
    ExternalIdentity.subject == subject,
    )
    identity = await db.scalar(statement)

    if identity is not None:
        identity.email = email
        identity.email_verified = True

        user = await db.get(User, identity.user_id)
        if user is None:
            raise RuntimeError("identity references missing user")

        return user

    user = User()
    db.add(user)
    await db.flush()

    identity = ExternalIdentity(
        user_id=user.id,
        issuer=issuer,
        subject=subject,
        email=email,
        email_verified=True,
    )
    db.add(identity)

    await assign_starter_quota(db, user_id=user.id)

    return user