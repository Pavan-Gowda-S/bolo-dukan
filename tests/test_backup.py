import sqlite3
import tempfile
import unittest
from pathlib import Path
import zipfile

from scripts.backup import backup_database, create_backup, rotate_backups


class TestBackup(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_backup_database_live_safe(self):
        db_src = self.tmp_path / "src.db"
        db_dst = self.tmp_path / "dst.db"

        conn = sqlite3.connect(str(db_src))
        with conn:
            conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, item TEXT)")
            conn.execute("INSERT INTO orders (item) VALUES ('Masala Dosa')")
        conn.close()

        success = backup_database(db_src, db_dst)
        self.assertTrue(success)
        self.assertTrue(db_dst.exists())

        chk_conn = sqlite3.connect(str(db_dst))
        row = chk_conn.execute("SELECT item FROM orders WHERE id=1").fetchone()
        chk_conn.close()
        self.assertEqual(row[0], "Masala Dosa")

    def test_backup_rotation(self):
        dest = self.tmp_path / "backups"
        dest.mkdir()
        for i in range(5):
            f = dest / f"bolo_dukaan_backup_2026-11-22_12000{i}.zip"
            f.write_text("test")

        deleted = rotate_backups(dest, keep=3)
        self.assertEqual(len(deleted), 2)
        remaining = list(dest.glob("bolo_dukaan_backup_*.zip"))
        self.assertEqual(len(remaining), 3)


if __name__ == "__main__":
    unittest.main()
