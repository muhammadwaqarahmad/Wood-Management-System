"""Roles and the permission matrix.

The UI (later phases) calls ``has_permission(user.role, Permission.X)``
to decide what to show, enable, or block. Keeping this here means the
rules live in one auditable place, not scattered across screens.
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    """The five roles from the plan. Values match ``User.role`` strings."""

    ADMIN = "Admin"
    MANAGER = "Manager"
    DATA_ENTRY = "Data Entry"
    ACCOUNTANT = "Accountant"
    VIEWER = "Viewer"


class Permission(str, Enum):
    MANAGE_USERS = "manage_users"          # create/edit users & roles
    MANAGE_SETTINGS = "manage_settings"    # locations, wood types, parties
    CREATE_TXN = "create_txn"
    EDIT_TXN = "edit_txn"
    EDIT_TRADE = "edit_trade"  # edit a saved buy+sell — Admin/Manager only
    VOID_TXN = "void_txn"
    MANAGE_PAYMENTS = "manage_payments"
    VIEW_LEDGERS = "view_ledgers"
    VIEW_DASHBOARD = "view_dashboard"
    VIEW_REPORTS = "view_reports"
    EXPORT_DATA = "export_data"
    BACKUP_RESTORE = "backup_restore"
    VIEW_AUDIT = "view_audit"
    DELETE_RECORD = "delete_record"  # hard delete — Admin only


_ALL: set[Permission] = set(Permission)

# Read-only bundle reused by several roles.
_VIEW_ONLY: set[Permission] = {
    Permission.VIEW_LEDGERS,
    Permission.VIEW_DASHBOARD,
    Permission.VIEW_REPORTS,
}

ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    # Full control of everything.
    Role.ADMIN: _ALL,
    # Runs day-to-day operations, but not user admin, backups, or hard delete.
    Role.MANAGER: _ALL
    - {
        Permission.MANAGE_USERS,
        Permission.BACKUP_RESTORE,
        Permission.DELETE_RECORD,
    },
    # Enters loads and payments; cannot void or change settings.
    Role.DATA_ENTRY: {
        Permission.CREATE_TXN,
        Permission.EDIT_TXN,
        Permission.MANAGE_PAYMENTS,
        Permission.VIEW_LEDGERS,
        Permission.VIEW_DASHBOARD,
    },
    # Money & reporting focus.
    Role.ACCOUNTANT: _VIEW_ONLY
    | {
        Permission.MANAGE_PAYMENTS,
        Permission.EXPORT_DATA,
        Permission.VIEW_AUDIT,
    },
    # Look, don't touch.
    Role.VIEWER: set(_VIEW_ONLY),
}


def has_permission(role: Role | str, permission: Permission) -> bool:
    """Return True if ``role`` is allowed to perform ``permission``."""
    if not isinstance(role, Role):
        try:
            role = Role(role)
        except ValueError:
            return False
    return permission in ROLE_PERMISSIONS.get(role, set())
