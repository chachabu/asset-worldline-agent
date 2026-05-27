import argparse

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import User
from app.services.bootstrap import create_database, seed_database
from app.services.security import hash_password


def init_db() -> None:
    settings = get_settings()
    create_database()
    with SessionLocal() as db:
        seed_database(db, settings)
    print("Database initialized.")


def create_admin(username: str, password: str) -> None:
    create_database()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user:
            user.password_hash = hash_password(password)
            user.is_active = True
        else:
            db.add(User(username=username, password_hash=hash_password(password), is_active=True))
        db.commit()
    print(f"Admin user ready: {username}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="asset-worldline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db")
    admin_parser = subparsers.add_parser("create-admin")
    admin_parser.add_argument("--username", required=True)
    admin_parser.add_argument("--password", required=True)
    args = parser.parse_args()

    if args.command == "init-db":
        init_db()
    elif args.command == "create-admin":
        create_admin(args.username, args.password)


if __name__ == "__main__":
    main()

