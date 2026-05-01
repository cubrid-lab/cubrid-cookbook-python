"""05_cubrid_upsert.py - CUBRID upsert patterns with sqlalchemy-cubrid DML helpers.

Demonstrates:
- ON DUPLICATE KEY UPDATE via sqlalchemy_cubrid.dml.insert
- REPLACE INTO via sqlalchemy_cubrid.dml.replace
- Practical differences in behavior for existing rows
"""

from __future__ import annotations

import importlib
from typing import final

from sqlalchemy import Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"


class Base(DeclarativeBase):
    pass


@final
class AppSetting(Base):
    __tablename__ = "cookbook_app_settings"

    setting_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    setting_val: Mapped[str] = mapped_column(String(200))
    enabled_flag: Mapped[int] = mapped_column(Integer, default=1)


def print_rows(session: Session, title: str) -> None:
    print(title)
    rows = session.scalars(select(AppSetting).order_by(AppSetting.setting_key)).all()
    for row in rows:
        print(
            f"setting_key={row.setting_key}, setting_val={row.setting_val}, enabled_flag={row.enabled_flag}"
        )


def main() -> None:
    engine = create_engine(DATABASE_URL)
    print("=== CUBRID ON DUPLICATE KEY UPDATE and REPLACE ===")

    try:
        Base.metadata.create_all(engine)
        print("[1] Created table cookbook_app_settings")

        with Session(engine) as session:
            cubrid_dml = importlib.import_module("sqlalchemy_cubrid.dml")
            cubrid_insert = cubrid_dml.insert
            cubrid_replace = cubrid_dml.replace

            print("\n[2] Insert baseline row")
            session.execute(
                cubrid_insert(AppSetting).values(
                    setting_key="app.name",
                    setting_val="Cookbook",
                    enabled_flag=1,
                )
            )
            session.commit()
            print_rows(session, "Current rows after initial insert:")

            print("\n[3] ON DUPLICATE KEY UPDATE for existing key")
            odku_stmt = cubrid_insert(AppSetting).values(
                setting_key="app.name",
                setting_val="Cookbook v2",
                enabled_flag=1,
            )
            odku_stmt = odku_stmt.on_duplicate_key_update(
                setting_val="Cookbook v2",
                enabled_flag=1,
            )
            session.execute(odku_stmt)
            session.commit()
            print_rows(session, "Rows after ODKU update:")

            print("\n[4] ON DUPLICATE KEY UPDATE for new key")
            odku_insert_stmt = cubrid_insert(AppSetting).values(
                setting_key="feature.search",
                setting_val="enabled",
                enabled_flag=1,
            )
            odku_insert_stmt = odku_insert_stmt.on_duplicate_key_update(
                setting_val="enabled",
                enabled_flag=1,
            )
            session.execute(odku_insert_stmt)
            session.commit()
            print_rows(session, "Rows after ODKU insert:")

            print("\n[5] REPLACE INTO for existing key")
            session.execute(
                cubrid_replace(AppSetting).values(
                    setting_key="feature.search",
                    setting_val="disabled",
                    enabled_flag=0,
                )
            )
            session.commit()
            print_rows(session, "Rows after REPLACE:")

        print("\nCUBRID upsert demo completed.")
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
        print("Cleanup complete.")


if __name__ == "__main__":
    main()
