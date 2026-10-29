"""Дамп PostgreSQL и пробное восстановление в отдельную БД."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
COMMAND = [
    "docker",
    "compose",
    "-p",
    "compas",
    "-f",
    str(ROOT / "docker-compose.yml"),
    "exec",
    "-T",
    "db",
]


def docker(args, **kwargs):
    return subprocess.run(COMMAND + args, cwd=ROOT, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["create", "verify", "restore-check"])
    parser.add_argument("file", nargs="?", type=Path)
    args = parser.parse_args()
    if args.command == "create":
        directory = ROOT / "backups"
        directory.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = directory / f"compas-{stamp}-{uuid.uuid4().hex[:8]}.dump"
        with path.open("xb") as output:
            docker(
                ["sh", "-c", 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'],
                stdout=output,
            )
        print(path)
        return
    if args.file is None or not args.file.is_file():
        parser.error("Specify an existing dump file")
    if args.command == "verify":
        with args.file.open("rb") as source:
            docker(["pg_restore", "--list"], stdin=source, stdout=subprocess.DEVNULL)
        print(
            "Archive structure is readable. Run restore-check to verify actual restoration."
        )
        return
    database = "compas_restore_" + uuid.uuid4().hex
    docker(["sh", "-c", 'exec createdb -U "$POSTGRES_USER" "$1"', "sh", database])
    with args.file.open("rb") as source:
        docker(
            [
                "sh",
                "-c",
                'exec pg_restore -U "$POSTGRES_USER" --no-owner --single-transaction -d "$1"',
                "sh",
                database,
            ],
            stdin=source,
        )
    docker(
        [
            "sh",
            "-c",
            'exec psql -U "$POSTGRES_USER" -d "$1" -v ON_ERROR_STOP=1 -c "SELECT version_num FROM alembic_version; SELECT COUNT(*) FROM users; SELECT COUNT(*) FROM test_result;"',
            "sh",
            database,
        ]
    )
    print("Restored into independent database:", database)


if __name__ == "__main__":
    main()
