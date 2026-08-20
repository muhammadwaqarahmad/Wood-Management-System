"""Backup & restore — drives timber.core.backup server-side over the API.

Read + write, all gated on BACKUP_RESTORE (the SAME permission the desktop
enforces). The browser moves files via download/upload; the server keeps the
same timestamped backup files the desktop creates, so a backup made on the
desktop restores on the web and vice-versa.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from timber.api.deps import require_permission
from timber.core import backup
from timber.core.permissions import Permission

router = APIRouter(prefix="/backup", tags=["backup"])
_ADMIN = require_permission(Permission.BACKUP_RESTORE)


def _entry(p: Path) -> dict:
    st = p.stat()
    return {
        "name": p.name,
        "when": datetime.fromtimestamp(st.st_mtime).isoformat(),
        "size_mb": round(st.st_size / (1024 * 1024), 2),
    }


@router.get("/status")
def status(_=Depends(_ADMIN)) -> dict:
    """Backup folder, auto-backup settings, last-backup time and the file list."""
    last = backup.last_backup_time()
    return {
        "backup_dir": str(backup.get_backup_dir()),
        "auto_on_close": backup.get_auto_on_close(),
        "interval_hours": backup.get_interval_hours(),
        "keep_days": backup.get_keep_days(),
        "last_backup": last.isoformat() if last else None,
        "backups": [_entry(p) for p in backup.list_backups()],
    }


@router.post("/now")
def create(_=Depends(_ADMIN)) -> dict:
    """Create a timestamped server-side backup (then prune by keep_days)."""
    try:
        p = backup.backup_now()
    except Exception as e:  # noqa: BLE001 - surface the real reason to the UI
        raise HTTPException(status_code=400, detail=str(e))
    try:
        backup.prune_backups(backup.get_keep_days())
    except Exception:  # noqa: BLE001 - pruning is best-effort
        pass
    return {"name": p.name}


@router.get("/download/{name}")
def download(name: str, _=Depends(_ADMIN)):
    """Stream a backup file to the browser. `name` is a base filename only."""
    safe = Path(name).name  # strip any path components (traversal guard)
    path = Path(backup.get_backup_dir()) / safe
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Backup not found.")
    return FileResponse(str(path), filename=safe, media_type="application/octet-stream")


class RestoreIn(BaseModel):
    name: str


@router.post("/restore")
def restore(body: RestoreIn, _=Depends(_ADMIN)) -> dict:
    """Restore a named backup that already lives in the backup folder."""
    safe = Path(body.name).name
    path = Path(backup.get_backup_dir()) / safe
    try:
        backup.restore_from(path)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.post("/restore-upload")
async def restore_upload(file: UploadFile = File(...), _=Depends(_ADMIN)) -> dict:
    """Restore from a file the user uploads from their browser."""
    safe = Path(file.filename or "upload.bak").name
    dest = Path(backup.get_backup_dir()) / safe
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(await file.read())
    try:
        backup.restore_from(dest)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


class SettingsIn(BaseModel):
    auto_on_close: bool | None = None
    interval_hours: int | None = None
    keep_days: int | None = None
    backup_dir: str | None = None


@router.post("/settings")
def save_settings(body: SettingsIn, _=Depends(_ADMIN)) -> dict:
    """Update auto-backup settings (and, optionally, the server backup folder)."""
    if body.auto_on_close is not None:
        backup.set_auto_on_close(body.auto_on_close)
    if body.interval_hours is not None:
        backup.set_interval_hours(body.interval_hours)
    if body.keep_days is not None:
        backup.set_keep_days(body.keep_days)
    if body.backup_dir:
        backup.set_backup_dir(body.backup_dir)
    return {"ok": True}
