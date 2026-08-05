"""Tests for backend-aware backup / list / restore / prune."""

import sqlite3
import subprocess
from datetime import datetime, timedelta

import pytest

from timber import config
from timber.core import app_settings, backup


@pytest.fixture
def sqlite_env(tmp_path, monkeypatch):
    db = tmp_path / "timber.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES ('hello')")
    conn.commit()
    conn.close()

    monkeypatch.setattr(config, "DB_BACKEND", "sqlite")
    monkeypatch.setattr(config, "SQLITE_PATH", db)
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "backups")
    # Isolate per-PC settings so a real settings.json can't affect tests.
    monkeypatch.setattr(app_settings, "_PATH", tmp_path / "settings.json")
    return tmp_path


def test_backup_and_list(sqlite_env):
    dest = backup.backup_now()
    assert dest.exists()
    assert backup.list_backups() == [dest]
    # the backup is a valid copy
    conn = sqlite3.connect(str(dest))
    assert conn.execute("SELECT v FROM t").fetchone()[0] == "hello"
    conn.close()


def test_restore(sqlite_env):
    dest = backup.backup_now()
    # corrupt the live db, then restore
    config.SQLITE_PATH.write_bytes(b"broken")
    backup.restore_from(dest)
    conn = sqlite3.connect(str(config.SQLITE_PATH))
    assert conn.execute("SELECT v FROM t").fetchone()[0] == "hello"
    conn.close()


def test_prune(sqlite_env):
    dest = backup.backup_now()
    old = datetime.now() - timedelta(days=40)
    import os

    os.utime(dest, (old.timestamp(), old.timestamp()))
    assert backup.prune_backups(keep_days=30) == 1
    assert backup.list_backups() == []


def test_auto_backup_creates_and_prunes(sqlite_env):
    backup.set_keep_days(30)
    # An old backup (distinct filename) that should be pruned by auto_backup.
    old = backup.backup_now().rename(
        backup.get_backup_dir() / "timber_20200101_000000.db"
    )
    import os
    ts = (datetime.now() - timedelta(days=40)).timestamp()
    os.utime(old, (ts, ts))

    dest = backup.auto_backup()
    assert dest is not None and dest.exists()
    files = backup.list_backups()
    assert old not in files          # old one pruned
    assert dest in files             # fresh one kept


def test_auto_backup_respects_min_gap(sqlite_env):
    first = backup.auto_backup()
    assert first is not None
    # A second call within the gap window is skipped (no duplicate spam).
    assert backup.auto_backup(min_gap_minutes=10) is None


def test_interval_backup_due(sqlite_env):
    backup.set_interval_hours(0)
    assert backup.interval_backup_due() is False   # disabled
    backup.set_interval_hours(6)
    assert backup.interval_backup_due() is True     # no backup yet -> due
    backup.backup_now()
    assert backup.interval_backup_due() is False    # just backed up -> not due


def test_last_backup_time(sqlite_env):
    assert backup.last_backup_time() is None
    backup.backup_now()
    assert backup.last_backup_time() is not None


def test_backup_dir_override(sqlite_env, tmp_path):
    # Pointing the backup folder elsewhere (e.g. a Google Drive folder)
    # is honoured by get_backup_dir / backup_now.
    gdrive = tmp_path / "GoogleDrive" / "TimberBackups"
    backup.set_backup_dir(gdrive)
    assert backup.get_backup_dir() == gdrive
    dest = backup.backup_now()
    assert dest.parent == gdrive
    assert dest.exists()


def test_postgres_backup_invokes_pg_dump(sqlite_env, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_BACKEND", "postgresql")
    monkeypatch.setattr(config, "PG_PASSWORD", "secret")
    monkeypatch.setattr(backup, "_find_pg_tool", lambda name: f"/usr/bin/{name}")

    captured = {}

    def fake_run(cmd, env=None, capture_output=False, text=False):
        captured["cmd"] = cmd
        captured["pgpassword"] = (env or {}).get("PGPASSWORD")
        # Simulate pg_dump writing the dump file at the -f path.
        out = cmd[cmd.index("-f") + 1]
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("-- dump")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(backup.subprocess, "run", fake_run)
    dest = backup.backup_now()
    assert dest.suffix == ".sql"
    assert dest.exists()
    assert "pg_dump" in captured["cmd"][0]
    assert "--clean" in captured["cmd"]
    assert captured["pgpassword"] == "secret"


def test_postgres_backup_reports_failure(sqlite_env, monkeypatch):
    monkeypatch.setattr(config, "DB_BACKEND", "postgresql")
    monkeypatch.setattr(backup, "_find_pg_tool", lambda name: f"/usr/bin/{name}")

    def fake_run(cmd, env=None, capture_output=False, text=False):
        return subprocess.CompletedProcess(cmd, 1, "", "connection refused")

    monkeypatch.setattr(backup.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="pg_dump failed"):
        backup.backup_now()
