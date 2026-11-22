"""Cross-platform backup utility for Bolo Dukaan.

Creates a safe snapshot of the SQLite database (using SQLite's online backup API,
safe while the server is live and taking orders) along with uploads and secrets,
bundled into a timestamped zip archive.

Usage:
    python scripts/backup.py
    python scripts/backup.py --dest D:\\backups --keep 30
    python scripts/backup.py --dry-run
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import zipfile

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "bolo_dukaan.db"
DEFAULT_DEST = DATA_DIR / "backups"
IST = timezone(timedelta(hours=5, minutes=30))


def backup_database(src_path: Path, dst_path: Path) -> bool:
    """Use SQLite's hot backup API to copy the database safely without locks."""
    if not src_path.exists():
        return False
    src_conn = sqlite3.connect(str(src_path), timeout=30.0)
    dst_conn = sqlite3.connect(str(dst_path))
    try:
        with dst_conn:
            src_conn.backup(dst_conn)
        return True
    finally:
        dst_conn.close()
        src_conn.close()


def create_backup(
    dest_dir: Path | None = None,
    keep: int = 14,
    dry_run: bool = False,
) -> Path | None:
    dest = Path(dest_dir) if dest_dir else DEFAULT_DEST
    now = datetime.now(IST)
    stamp = now.strftime("%Y-%m-%d_%H%M%S")
    archive_name = f"bolo_dukaan_backup_{stamp}.zip"
    archive_path = dest / archive_name

    if dry_run:
        print(f"[DRY RUN] Would create backup at: {archive_path}")
        print(f"[DRY RUN] Would prune archives keeping newest {keep}")
        return archive_path

    dest.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="bolo_backup_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        has_db = False

        if DB_PATH.exists():
            tmp_db = tmp_path / "bolo_dukaan.db"
            if backup_database(DB_PATH, tmp_db):
                has_db = True
                print(f"  [OK] Hot SQLite database snapshot taken ({tmp_db.stat().st_size // 1024} KB)")

        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if has_db:
                zf.write(tmp_path / "bolo_dukaan.db", arcname="bolo_dukaan.db")

            uploads_dir = DATA_DIR / "uploads"
            if uploads_dir.exists() and uploads_dir.is_dir():
                count = 0
                for f in uploads_dir.rglob("*"):
                    if f.is_file():
                        arc_rel = f.relative_to(DATA_DIR)
                        zf.write(f, arcname=str(arc_rel))
                        count += 1
                if count:
                    print(f"  [OK] Packed {count} uploaded file(s)")

            secret_key = DATA_DIR / "secret.key"
            if secret_key.exists():
                zf.write(secret_key, arcname="secret.key")
                print("  [OK] Packed secret.key")

            manifest = {
                "created_at": now.isoformat(),
                "has_db": has_db,
                "version": 1,
            }
            zf.writestr("manifest.txt", f"Bolo Dukaan Backup\nCreated: {now.isoformat()}\n")

    print(f"\nBackup successfully created: {archive_path} ({archive_path.stat().st_size // 1024} KB)")

    # Rotate old backups
    rotate_backups(dest, keep=keep)
    return archive_path


def rotate_backups(dest: Path, keep: int = 14) -> list[Path]:
    """Delete older backups exceeding the retention count."""
    backups = sorted(dest.glob("bolo_dukaan_backup_*.zip"), key=lambda p: p.stat().st_mtime)
    deleted: list[Path] = []
    if len(backups) > keep:
        to_delete = backups[: len(backups) - keep]
        for b in to_delete:
            try:
                b.unlink()
                deleted.append(b)
                print(f"  [PRUNED] Removed old backup: {b.name}")
            except OSError as e:
                print(f"  [WARN] Failed to delete {b.name}: {e}")
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a full backup of Bolo Dukaan database and data.")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST, help=f"Destination directory (default: {DEFAULT_DEST})")
    parser.add_argument("--keep", type=int, default=14, help="Number of backups to keep (default: 14)")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without modifying files")
    args = parser.parse_args()

    print("\n  Bolo Dukaan Backup Utility\n")
    try:
        archive = create_backup(dest_dir=args.dest, keep=args.keep, dry_run=args.dry_run)
        if archive:
            return 0
        return 1
    except Exception as e:
        print(f"  [ERROR] Backup failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
