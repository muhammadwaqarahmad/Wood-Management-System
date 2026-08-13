"""Tests for password hashing, login, and the permission matrix."""

from timber.core.auth import authenticate, create_user
from timber.core.permissions import Permission, Role, has_permission
from timber.core.security import hash_password, verify_password


def test_hash_is_not_plaintext_and_verifies():
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password("secret123", h) is True
    assert verify_password("wrong", h) is False


def test_verify_handles_garbage_hash():
    assert verify_password("anything", "") is False


def test_create_and_authenticate(session):
    create_user(session, "ali", "pass123", role=Role.MANAGER, full_name="Ali")
    user = authenticate(session, "ali", "pass123")
    assert user is not None
    assert user.role == "Manager"


def test_authenticate_wrong_password(session):
    create_user(session, "ali", "pass123")
    assert authenticate(session, "ali", "nope") is None


def test_authenticate_unknown_user(session):
    assert authenticate(session, "ghost", "x") is None


def test_inactive_user_cannot_login(session):
    user = create_user(session, "ali", "pass123")
    user.is_active = False
    session.flush()
    assert authenticate(session, "ali", "pass123") is None


def test_admin_has_all_permissions():
    for perm in Permission:
        assert has_permission(Role.ADMIN, perm)


def test_viewer_is_read_only():
    assert has_permission(Role.VIEWER, Permission.VIEW_LEDGERS)
    assert not has_permission(Role.VIEWER, Permission.CREATE_TXN)
    assert not has_permission(Role.VIEWER, Permission.MANAGE_USERS)


def test_role_accepts_string():
    # User.role is stored as a string in the DB.
    assert has_permission("Accountant", Permission.MANAGE_PAYMENTS)
    assert not has_permission("Accountant", Permission.MANAGE_USERS)


def test_unknown_role_denied():
    assert not has_permission("Wizard", Permission.VIEW_LEDGERS)
