"""01_alembic_programmatic.py - Alembic migrations against CUBRID, programmatically.

Demonstrates:
- Using ``alembic.command`` and ``alembic.config.Config`` from Python
- Auto-discovery of the CUBRID dialect (``CubridImpl``)
- Autogenerating a migration from SQLAlchemy ORM metadata
- Upgrading and downgrading programmatically

sqlalchemy-cubrid ships a ``CubridImpl`` (registered via the
``alembic.ddl`` entry point) that knows about CUBRID-specific DDL
behavior. Because CUBRID does NOT support transactional DDL
(``transactional_ddl = False``), Alembic will issue each DDL statement
in its own implicit auto-commit.

This recipe runs Alembic against a TEMP DIRECTORY so it is fully
self-contained: no project-level ``alembic.ini`` required.

Run:
    python 01_alembic_programmatic.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy import Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"
TARGET_METADATA_TABLE = "cookbook_alembic_demo"


class Base(DeclarativeBase):
    pass


class CookbookAlembicDemo(Base):
    """The ORM model Alembic will autogenerate a migration for."""

    __tablename__ = TARGET_METADATA_TABLE

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(200), nullable=False)


def _build_alembic_config(workdir: Path) -> Any:
    """Construct an in-memory Alembic Config that points at our DB and env."""
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(workdir / "migrations"))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    # Render importable migration modules (not lazy .pyc blobs).
    cfg.set_main_option("prepend_sys_path", str(workdir))
    return cfg


def _write_env_py(workdir: Path) -> None:
    """Write a minimal ``env.py`` that uses our declarative metadata."""
    migrations_dir = workdir / "migrations"
    versions_dir = migrations_dir / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    env_py = '''
"""Alembic environment for the cookbook recipe."""
from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Import the ORM Base whose metadata Alembic will compare against.
import sys
sys.path.insert(0, %r)

from 01_alembic_programmatic import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
''' % str(workdir)

    (migrations_dir / "env.py").write_text(env_py)

    # Minimal script.py.mako so Alembic can render new revision files.
    script_template = (
        '"""${message}',
        "",
        "Revision ID: ${up_revision}",
        "Revises: ${down_revision}",
        "Create Date: ${create_date}",
        '"""',
        "from alembic import op",
        "import sqlalchemy as sa",
        "",
        "",
        "revision = ${repr(up_revision)}"
        "down_revision = ${repr(down_revision)}"
        "branch_labels = ${repr(branch_labels)}"
        "depends_on = ${repr(depends_on)}"
        "",
        "",
        "def upgrade() -> None:",
        '    ${upgrades if upgrades else "pass"}',
        "",
        "def downgrade() -> None:",
        '    ${downgrades if downgrades else "pass"}',
    )
    (migrations_dir / "script.py.mako").write_text("\n".join(script_template))


def main() -> None:
    import alembic.command  # local import: keep top-level importable

    print("=== Alembic Programmatic Migration Demo (CUBRID) ===")
    print()

    # Make sure the ORM model module is importable under its real filename.
    workdir = Path(tempfile.mkdtemp(prefix="cookbook_alembic_"))
    print(f"[1] Working directory: {workdir}")

    # Drop any leftover table so the demo is deterministic.
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        conn.exec_driver_sql(f"DROP TABLE IF EXISTS {TARGET_METADATA_TABLE}")
    engine.dispose()
    print(f"[2] Ensured table {TARGET_METADATA_TABLE} does not exist")

    _write_env_py(workdir)
    cfg = _build_alembic_config(workdir)
    print("[3] Wrote env.py and script.py.mako")

    # ------------------------------------------------------------------
    # Step 4: initialize the migrations folder (creates the versions/ dir).
    # ------------------------------------------------------------------
    alembic.command.init(cfg, directory=str(workdir / "migrations"))
    print("[4] Initialized Alembic migrations folder")

    # ------------------------------------------------------------------
    # Step 5: autogenerate a migration from the ORM metadata.
    #
    # Alembic inspects the live DB schema, compares it against
    # Base.metadata, and writes a migration revision file with the
    # upgrade() and downgrade() bodies filled in.
    # ------------------------------------------------------------------
    alembic.command.revision(
        cfg,
        message="create cookbook_alembic_demo",
        autogenerate=True,
    )
    print("[5] Autogenerated migration revision")

    # ------------------------------------------------------------------
    # Step 6: apply the migration (upgrade head).
    # ------------------------------------------------------------------
    alembic.command.upgrade(cfg, "head")
    print("[6] Upgraded to head (table should now exist)")

    # Verify the table exists via SQLAlchemy Inspector.
    engine = create_engine(DATABASE_URL)
    from sqlalchemy import inspect

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    engine.dispose()
    if TARGET_METADATA_TABLE in tables:
        print(f"[7] Verified: {TARGET_METADATA_TABLE} now exists in the DB")
    else:
        print(f"[7] WARNING: table {TARGET_METADATA_TABLE} not found after upgrade")

    # ------------------------------------------------------------------
    # Step 7: downgrade one revision (drops the table).
    # ------------------------------------------------------------------
    alembic.command.downgrade(cfg, "-1")
    print("[8] Downgraded one revision (table should be dropped)")

    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)
    tables_after = inspector.get_table_names()
    engine.dispose()
    if TARGET_METADATA_TABLE not in tables_after:
        print(f"[9] Verified: {TARGET_METADATA_TABLE} dropped after downgrade")
    else:
        print("[9] WARNING: table still present after downgrade")

    print()
    print("--- CUBRID + Alembic notes ---")
    print("  * CubridImpl is auto-discovered via the alembic.ddl entry point.")
    print("  * transactional_ddl = False  -> each DDL statement auto-commits.")
    print("  * No native SEQUENCE support  -> migrations use AUTO_INCREMENT.")
    print("  * Identifiers are lowercase-folded with a 254-char max.")
    print()
    print("For a real project layout (alembic.ini at repo root), see README.md.")


if __name__ == "__main__":
    main()
