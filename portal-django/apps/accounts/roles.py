from enum import StrEnum


class SystemRole(StrEnum):
    REVIEWER = "reviewer"
    OPERATOR = "operator"


def _is_active_user(user) -> bool:
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
    )


def has_system_role(user, role: SystemRole) -> bool:
    if not _is_active_user(user):
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=role.value).exists()


def can_review_requests(user) -> bool:
    return has_system_role(user, SystemRole.REVIEWER)


def can_execute_operations(user) -> bool:
    return has_system_role(user, SystemRole.OPERATOR)


def can_assign_system_roles(user) -> bool:
    return _is_active_user(user) and user.is_superuser
