"""Create an online-consistent backup of the SQLite workflow state database."""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from tempfile import NamedTemporaryFile


def backup_sqlite_state_store(source: Path, destination: Path) -> None:
    """Use SQLite's backup API so WAL-mode writes remain safe during backup."""
    if not source.is_file():
        raise FileNotFoundError(f"SQLite state-store database not found: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(source)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()


def restore_sqlite_state_store(backup: Path, destination: Path, *, replace: bool = False) -> None:
    """Restore a checked SQLite backup without implicitly overwriting live state."""
    if not backup.is_file():
        raise FileNotFoundError(f"SQLite state-store backup not found: {backup}")
    if backup.resolve() == destination.resolve():
        raise ValueError("Backup and restore destination must be different files")
    if destination.exists() and not replace:
        raise FileExistsError(f"Restore destination already exists: {destination}; pass replace=True to overwrite it")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".restore",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

        source_connection = sqlite3.connect(backup)
        try:
            destination_connection = sqlite3.connect(temporary_path)
            try:
                source_connection.backup(destination_connection)
                integrity = destination_connection.execute("PRAGMA integrity_check").fetchone()
                if integrity != ("ok",):
                    raise sqlite3.DatabaseError(f"Restore integrity check failed: {integrity!r}")
            finally:
                destination_connection.close()
        finally:
            source_connection.close()
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up or restore the SQLite workflow state-store database")
    parser.add_argument("--source", required=True, type=Path, help="Source database or backup file")
    parser.add_argument("--destination", required=True, type=Path, help="Destination backup or restored database file")
    parser.add_argument("--restore", action="store_true", help="Restore --source into --destination")
    parser.add_argument("--replace", action="store_true", help="Allow --restore to replace an existing destination")
    args = parser.parse_args()
    if args.restore:
        restore_sqlite_state_store(args.source, args.destination, replace=args.replace)
    else:
        backup_sqlite_state_store(args.source, args.destination)


if __name__ == "__main__":
    main()
