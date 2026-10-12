import pytest
from app.compute.models import ComputePlan, UserQuota
from app.identity.models import ExternalIdentity
from app.identity.services import get_or_create_user
from app.users.models import User
from sqlalchemy import select


@pytest.mark.asyncio
async def test_first_login_creates_user_identity_and_starter_quota(db, user) -> None:
    # Act выполнен фикстурой user: get_or_create_user по новой identity.
    users = list(await db.scalars(select(User)))
    identities = list(await db.scalars(select(ExternalIdentity)))

    assert len(users) == 1
    assert len(identities) == 1

    identity = identities[0]
    assert identity.user_id == user.id
    assert identity.issuer == "issuer"
    assert identity.subject == "subject"
    assert identity.email == "email@example.com"
    assert identity.email_verified is True

    quota = await db.scalar(
        select(UserQuota).where(UserQuota.user_id == user.id)
    )
    assert quota is not None

    plan = await db.get(ComputePlan, quota.compute_plan_id)
    assert plan.code == "starter"


@pytest.mark.asyncio
async def test_repeated_login_returns_same_user_without_duplicates(db, user) -> None:
    second = await get_or_create_user(
        db=db,
        issuer="issuer",
        subject="subject",
        email="email@example.com",
    )

    assert second.id == user.id

    users = list(await db.scalars(select(User)))
    identities = list(await db.scalars(select(ExternalIdentity)))
    assert len(users) == 1
    assert len(identities) == 1


@pytest.mark.asyncio
async def test_repeated_login_syncs_email_of_external_identity(db, user) -> None:
    second = await get_or_create_user(
        db=db,
        issuer="issuer",
        subject="subject",
        email="new-email@example.com",
    )

    identity = await db.scalar(
        select(ExternalIdentity).where(ExternalIdentity.user_id == second.id)
    )

    assert second.id == user.id
    assert identity.email == "new-email@example.com"
    assert identity.email_verified is True


@pytest.mark.asyncio
async def test_different_subject_creates_new_user(db, user) -> None:
    second = await get_or_create_user(
        db=db,
        issuer="issuer",
        subject="another-subject",
        email="email@example.com",
    )

    assert second.id != user.id

    users = list(await db.scalars(select(User)))
    identities = list(await db.scalars(select(ExternalIdentity)))
    assert len(users) == 2
    assert len(identities) == 2
