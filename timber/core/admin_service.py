"""Management services: validated create/update/deactivate for parties,
locations, wood types, and users. Each writes an audit-log row; the
caller owns the transaction (commit).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from timber.core import auth
from timber.core.audit import log_action
from timber.core.permissions import Role
from timber.core.security import hash_password
from timber.db.models import (
    BapariTxn,
    FactoryTxn,
    Location,
    Party,
    PartyBank,
    PartyPhone,
    Payment,
    User,
    WoodType,
)
from timber.db.models.party import PARTY_BAPARI, PARTY_FACTORY


def _set_phones(party: Party, phones: list[str] | None) -> None:
    if phones is None:
        return
    party.phones = [
        PartyPhone(phone=p.strip()) for p in phones if p and p.strip()
    ]


def _set_links(session: Session, party: Party, factory_ids: list[int] | None) -> None:
    """Set a bapari's linked factories (no-op for factories)."""
    if factory_ids is None or party.party_type != PARTY_BAPARI:
        return
    factories = []
    for fid in factory_ids:
        f = session.get(Party, fid)
        if f is not None and f.party_type == PARTY_FACTORY:
            factories.append(f)
    party.linked_factories = factories


def _set_supplier_links(
    session: Session, party: Party, bapari_ids: list[int] | None
) -> None:
    """Set which suppliers link to this FACTORY (no-op for suppliers).

    It is the same supplier<->factory table, edited from the other end. The
    factory's own ``linked_baparis`` relationship is view-only, so the write
    goes through each supplier's ``linked_factories`` list.
    """
    if bapari_ids is None or party.party_type != PARTY_FACTORY:
        return
    wanted = set(bapari_ids)
    suppliers = session.scalars(
        select(Party).where(Party.party_type == PARTY_BAPARI)
    ).all()
    for sup in suppliers:
        linked = sup.id in wanted
        already = any(f.id == party.id for f in sup.linked_factories)
        if linked and not already:
            sup.linked_factories.append(party)
        elif not linked and already:
            sup.linked_factories = [
                f for f in sup.linked_factories if f.id != party.id
            ]


def _set_banks(party: Party, banks: list[dict] | None) -> None:
    if banks is None:
        return
    rows = []
    for b in banks:
        # Skip completely empty bank rows.
        if not any((b.get(k) or "").strip() for k in
                   ("account_title", "bank_name", "iban", "account_number")):
            continue
        rows.append(
            PartyBank(
                account_title=(b.get("account_title") or None),
                bank_name=(b.get("bank_name") or None),
                iban=(b.get("iban") or None),
                account_number=(b.get("account_number") or None),
            )
        )
    party.banks = rows


# --- simple name lookups (locations, wood types) --------------------
def create_lookup(session: Session, model: type, name: str, created_by=None):
    name = (name or "").strip()
    if not name:
        raise ValueError("Name is required.")
    if session.scalar(select(model).where(model.name == name)):
        raise ValueError("That name already exists.")
    obj = model(name=name)
    session.add(obj)
    session.flush()
    log_action(session, created_by, "create", model.__tablename__, obj.id, name)
    return obj


def rename_lookup(session: Session, model: type, obj_id: int, name: str, created_by=None):
    name = (name or "").strip()
    if not name:
        raise ValueError("Name is required.")
    obj = session.get(model, obj_id)
    if obj is None:
        raise ValueError("Item not found.")
    obj.name = name
    session.flush()
    log_action(session, created_by, "update", model.__tablename__, obj_id, name)
    return obj


def set_lookup_rates(
    session: Session, model: type, obj_id: int,
    supplier_rate=None, factory_rate=None, created_by=None,
):
    """Set a wood type's default rates. 0 means 'no default'.

    Either side may be passed on its own; the other is left as it was.
    """
    from decimal import InvalidOperation

    from timber.core.calculations import money

    obj = session.get(model, obj_id)
    if obj is None:
        raise ValueError("Item not found.")
    if not hasattr(obj, "default_supplier_rate"):
        raise ValueError("This item does not have rates.")

    def _clean(value, label):
        try:
            v = money(value or 0)
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError(f"{label} must be a number.")
        if v < Decimal("0"):
            raise ValueError(f"{label} cannot be negative.")
        return v

    if supplier_rate is not None:
        obj.default_supplier_rate = _clean(supplier_rate, "Supplier rate")
    if factory_rate is not None:
        obj.default_factory_rate = _clean(factory_rate, "Factory rate")
    session.flush()
    log_action(
        session, created_by, "update", model.__tablename__, obj_id,
        f"supplier_rate={obj.default_supplier_rate} "
        f"factory_rate={obj.default_factory_rate}",
    )
    return obj


def set_lookup_active(session: Session, model: type, obj_id: int, active: bool, created_by=None):
    obj = session.get(model, obj_id)
    if obj is None:
        raise ValueError("Item not found.")
    obj.is_active = active
    session.flush()
    action = "activate" if active else "deactivate"
    log_action(session, created_by, action, model.__tablename__, obj_id)
    return obj


_LOOKUP_FK = {"locations": "location_id", "wood_types": "wood_type_id"}


def delete_lookup(session: Session, model: type, obj_id: int, created_by=None) -> None:
    """Permanently delete a location / wood type. Blocked if it's used in
    any trade (deactivate instead)."""
    obj = session.get(model, obj_id)
    if obj is None:
        raise ValueError("Item not found.")
    col = _LOOKUP_FK.get(model.__tablename__)
    if col:
        used = (
            session.scalar(select(BapariTxn.id).where(getattr(BapariTxn, col) == obj_id).limit(1))
            or session.scalar(select(FactoryTxn.id).where(getattr(FactoryTxn, col) == obj_id).limit(1))
        )
        if used:
            raise ValueError(
                "Cannot delete: it is used in trades. Deactivate it instead."
            )
    name = obj.name
    session.delete(obj)
    session.flush()
    log_action(session, created_by, "delete", model.__tablename__, obj_id, name)


# --- parties --------------------------------------------------------
def _validate_party_type(party_type: str) -> str:
    if party_type not in (PARTY_BAPARI, PARTY_FACTORY):
        raise ValueError("Party type must be bapari or factory.")
    return party_type


def resolve_names(
    name: str | None, name_en: str | None, name_ur: str | None
) -> tuple[str, str]:
    """Work out the English + Urdu name from whatever was supplied. If only a
    single ``name`` is given it is used for the current language and mirrored
    to the other, so the row always shows in both languages."""
    from timber import i18n

    en = (name_en or "").strip() or None
    ur = (name_ur or "").strip() or None
    if not (en or ur):
        single = (name or "").strip()
        if not single:
            raise ValueError("Name is required.")
        if i18n.get_language() == "ur":
            ur = single
        else:
            en = single
    # Mirror the missing side so the row is never blank in either language.
    return (en or ur), (ur or en)


def create_party(
    session: Session,
    *,
    name: str | None = None,
    name_en: str | None = None,
    name_ur: str | None = None,
    party_type: str,
    email: str | None = None,
    address: str | None = None,
    credit_days: int | None = None,
    location_id: int | None = None,
    opening_balance: Any = 0,
    phones: list[str] | None = None,
    banks: list[dict] | None = None,
    linked_factory_ids: list[int] | None = None,
    linked_bapari_ids: list[int] | None = None,
    created_by=None,
) -> Party:
    en, ur = resolve_names(name, name_en, name_ur)
    _validate_party_type(party_type)
    party = Party(
        party_type=party_type,
        email=(email or None),
        address=(address or None),
        credit_days=credit_days,
        location_id=location_id,
        opening_balance=Decimal(str(opening_balance or 0)),
    )
    party.set_names(en=en, ur=ur)
    _set_phones(party, phones)
    _set_banks(party, banks)
    session.add(party)
    session.flush()
    _set_links(session, party, linked_factory_ids)
    _set_supplier_links(session, party, linked_bapari_ids)
    log_action(session, created_by, "create", "parties", party.id, party.name)
    return party


def update_party(
    session: Session,
    party_id: int,
    *,
    name: str | None = None,
    name_en: str | None = None,
    name_ur: str | None = None,
    email: str | None = None,
    address: str | None = None,
    credit_days: int | None = None,
    location_id: int | None = None,
    opening_balance: Any = None,
    phones: list[str] | None = None,
    banks: list[dict] | None = None,
    linked_factory_ids: list[int] | None = None,
    linked_bapari_ids: list[int] | None = None,
    update_credit_days: bool = False,
    created_by=None,
) -> Party:
    party = session.get(Party, party_id)
    if party is None:
        raise ValueError("Party not found.")
    # Bilingual names: set whichever were provided (each language edited on
    # its own), keeping the physical fallback in sync.
    if name_en is not None or name_ur is not None:
        en = name_en.strip() if name_en is not None else (party.name_en or "")
        ur = name_ur.strip() if name_ur is not None else (party.name_ur or "")
        if not (en or ur):
            raise ValueError("Name is required.")
        party.set_names(en=(en or ur), ur=(ur or en))
    elif name is not None:
        if not name.strip():
            raise ValueError("Name is required.")
        party.name = name.strip()
    if email is not None:
        party.email = email or None
    if address is not None:
        party.address = address or None
    # credit_days can legitimately be set to None, so use an explicit flag.
    if update_credit_days:
        party.credit_days = credit_days
    if location_id is not None:
        party.location_id = location_id or None
    if opening_balance is not None:
        party.opening_balance = Decimal(str(opening_balance))
    _set_phones(party, phones)
    _set_banks(party, banks)
    _set_links(session, party, linked_factory_ids)
    _set_supplier_links(session, party, linked_bapari_ids)
    session.flush()
    log_action(session, created_by, "update", "parties", party_id, party.name)
    return party


def delete_party(session: Session, party_id: int, created_by=None) -> None:
    """Permanently delete a party. Blocked if it has any transactions or
    payments (deactivate those instead, to preserve history)."""
    party = session.get(Party, party_id)
    if party is None:
        raise ValueError("Party not found.")
    referenced = (
        session.scalar(select(BapariTxn.id).where(BapariTxn.party_id == party_id).limit(1))
        or session.scalar(select(FactoryTxn.id).where(FactoryTxn.party_id == party_id).limit(1))
        or session.scalar(select(Payment.id).where(Payment.party_id == party_id).limit(1))
    )
    if referenced:
        raise ValueError(
            "Cannot delete: this party has transactions/payments. "
            "Deactivate it instead."
        )
    name = party.name
    session.delete(party)
    session.flush()
    log_action(session, created_by, "delete", "parties", party_id, name)


def set_party_active(session: Session, party_id: int, active: bool, created_by=None) -> Party:
    party = session.get(Party, party_id)
    if party is None:
        raise ValueError("Party not found.")
    party.is_active = active
    session.flush()
    log_action(
        session, created_by, "activate" if active else "deactivate", "parties", party_id
    )
    return party


# --- users ----------------------------------------------------------
def create_user_account(
    session: Session,
    *,
    username: str,
    password: str,
    role: Role | str = Role.VIEWER,
    full_name: str | None = None,
    created_by=None,
) -> User:
    username = (username or "").strip()
    if not username:
        raise ValueError("Username is required.")
    if not password:
        raise ValueError("Password is required.")
    if session.scalar(select(User).where(User.username == username)):
        raise ValueError("That username already exists.")
    user = auth.create_user(
        session, username, password, role=role, full_name=full_name
    )
    log_action(session, created_by, "create", "users", user.id, username)
    return user


def update_user(
    session: Session,
    user_id: int,
    *,
    role: Role | str | None = None,
    full_name: str | None = None,
    is_active: bool | None = None,
    created_by=None,
) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise ValueError("User not found.")
    if role is not None:
        user.role = role.value if isinstance(role, Role) else Role(role).value
    if full_name is not None:
        user.full_name = full_name or None
    if is_active is not None:
        user.is_active = is_active
    session.flush()
    log_action(session, created_by, "update", "users", user_id, user.username)
    return user


def delete_user(session: Session, user_id: int, created_by=None) -> None:
    """Delete a user. Blocked for your own account, the last active admin,
    or a user who already has recorded activity (deactivate instead)."""
    from sqlalchemy.exc import IntegrityError

    user = session.get(User, user_id)
    if user is None:
        raise ValueError("User not found.")
    if created_by is not None and user_id == created_by:
        raise ValueError("You cannot delete your own account.")
    if user.role == Role.ADMIN.value:
        others = session.scalar(
            select(User.id).where(
                User.role == Role.ADMIN.value,
                User.is_active.is_(True),
                User.id != user_id,
            ).limit(1)
        )
        if not others:
            raise ValueError("Cannot delete the last admin.")
    username = user.username
    try:
        session.delete(user)
        session.flush()
    except IntegrityError:
        session.rollback()
        raise ValueError(
            "Cannot delete: this user has recorded activity. Deactivate instead."
        )
    log_action(session, created_by, "delete", "users", user_id, username)


def reset_password(session: Session, user_id: int, new_password: str, created_by=None) -> User:
    if not new_password:
        raise ValueError("Password is required.")
    user = session.get(User, user_id)
    if user is None:
        raise ValueError("User not found.")
    user.password_hash = hash_password(new_password)
    session.flush()
    log_action(session, created_by, "reset_password", "users", user_id)
    return user
