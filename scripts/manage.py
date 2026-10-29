"""Управление аккаунтами и каталогом: python -m scripts.manage --help."""

import argparse
import asyncio
import getpass
import uuid
from sqlalchemy import select
from src.database import async_session_maker, engine
from src.utils.db_manager import DBManager
from src.models.users import UsersOrm
from src.schemas.users import UserRequestAdd
from src.services.auth import AuthService
from src.services.catalog import seed_catalog


async def run(args):
    try:
        async with DBManager(async_session_maker) as db:
            if args.command == "seed":
                print(await seed_catalog(db))
                return
            email = input("Email: ").strip()
            if args.command == "set-role":
                user = (
                    await db.session.execute(
                        select(UsersOrm).where(UsersOrm.email == email)
                    )
                ).scalar_one_or_none()
                if user is None:
                    raise SystemExit("Account not found")
                user.role_id = {"user": 1, "psychologist": 2, "admin": 0}[args.role]
                await db.commit()
                print("Role updated; sign in again")
                return
            username = input("Name: ").strip()
            password = getpass.getpass("Password (at least 8 characters): ")
            confirm = getpass.getpass("Repeat password: ")
            data = UserRequestAdd(
                email=email,
                username=username,
                gender="not specified",
                password=password,
                confirm_password=confirm,
            )
            if data.password != data.confirm_password:
                raise SystemExit("Passwords do not match")
            if await db.users.get_one_or_none(email=data.email):
                raise SystemExit("Account already exists; no changes made")
            db.session.add(
                UsersOrm(
                    id=uuid.uuid4(),
                    username=data.username,
                    email=data.email,
                    gender=data.gender,
                    hashed_password=AuthService().hash_password(data.password),
                    role_id=0,
                )
            )
            await db.commit()
            print("Admin created")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("create-admin")
    sub.add_parser("seed")
    roles = sub.add_parser("set-role")
    roles.add_argument("role", choices=["user", "psychologist", "admin"])
    asyncio.run(run(parser.parse_args()))
