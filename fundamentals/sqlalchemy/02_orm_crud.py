"""02_orm_crud.py - Full ORM CRUD lifecycle with SQLAlchemy 2.0.

Demonstrates:
- DeclarativeBase and mapped_column model definition
- Insert/list/update/delete flow with Session
- Table create/drop handled inside one runnable script
"""

from __future__ import annotations

from typing import final

from sqlalchemy import Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"


class Base(DeclarativeBase):
    pass


@final
class User(Base):
    __tablename__ = "cookbook_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    email: Mapped[str] = mapped_column(String(120), unique=True)
    active_flag: Mapped[int] = mapped_column(Integer, default=1)


def main() -> None:
    engine = create_engine(DATABASE_URL)
    print("=== SQLAlchemy ORM CRUD ===")

    try:
        print("[1] Creating table cookbook_users")
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            print("\n[2] INSERT users")
            users = [
                User(username="alice", email="alice@example.com", active_flag=1),
                User(username="bob", email="bob@example.com", active_flag=1),
                User(username="carol", email="carol@example.com", active_flag=0),
            ]
            session.add_all(users)
            session.commit()
            print(f"Inserted {len(users)} users")

            print("\n[3] LIST users")
            all_users = session.scalars(select(User).order_by(User.id)).all()
            for user in all_users:
                print(
                    f"id={user.id}, username={user.username}, email={user.email}, active_flag={user.active_flag}"
                )

            print("\n[4] UPDATE bob -> active_flag=0")
            bob = session.scalar(select(User).where(User.username == "bob"))
            if bob is not None:
                bob.active_flag = 0
                session.commit()
                print(
                    f"Updated user id={bob.id}, username={bob.username}, active_flag={bob.active_flag}"
                )

            print("\n[5] DELETE carol")
            carol = session.scalar(select(User).where(User.username == "carol"))
            if carol is not None:
                session.delete(carol)
                session.commit()
                print(f"Deleted user id={carol.id}, username={carol.username}")

            print("\n[6] FINAL LIST")
            remaining = session.scalars(select(User).order_by(User.id)).all()
            for user in remaining:
                print(
                    f"id={user.id}, username={user.username}, email={user.email}, active_flag={user.active_flag}"
                )

        print("\nCRUD demo completed.")
    finally:
        print("Dropping table cookbook_users")
        Base.metadata.drop_all(engine)
        engine.dispose()
        print("Cleanup complete.")


if __name__ == "__main__":
    main()
