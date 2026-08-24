"""alembic_programmatic.py - Alembic migrations against CUBRID, programmatically.

Demonstrates:
- Using ``alembic.command`` and ``alembic.config.Config`` from Python
- Registering the CUBRID dialect impl (``CubridImpl``) so autogenerate works
- Autogenerating a migration from SQLAlchemy ORM metadata
- Upgrading and downgrading programmatically

sqlalchemy-cubrid ships a ``CubridImpl`` (declared via the ``alembic.ddl``
entry point) that knows about CUBRID-specific DDL behavior. Alembic does not
import that entry point automatically, so ``env.py`` imports
``sqlalchemy_cubrid.alembic_impl`` to register it. Because CUBRID does NOT
support transactional DDL (``transactional_ddl = False``), Alembic issues each
DDL statement in its own implicit auto-commit.

This recipe runs Alembic against a TEMP DIRECTORY so it is fully
self-contained: no project-level ``alembic.ini`` required. Because the demo
database is shared with other recipes, ``env.py`` restricts autogenerate to the
single demo table via an ``include_name`` filter, so it never tries to drop
unrelated tables. For repeatable runs the script drops both the demo table
(``cookbook_alembic_demo``) and Alembic's own bookkeeping table
(``alembic_version``) in ``testdb`` before and after the migration; no other
schema in ``testdb`` is touched.

Run:
    python alembic_programmatic.py
"""

from __future__ import annotations

import contextlib
import io
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


# env.py restricts autogenerate to the demo table, registers CubridImpl, and
# imports the ORM Base whose metadata Alembic compares against. %r is filled
# with the directory that holds this module so the import resolves.
_ENV_PY_TEMPLATE = '''
"""Alembic environment for the cookbook recipe."""
from __future__ import annotations

import sys

from sqlalchemy import engine_from_config, pool

from alembic import context

# Register the CUBRID Alembic impl so context.configure() finds a "cubrid"
# dialect implementation (Alembic does not load the entry point on its own).
import sqlalchemy_cubrid.alembic_impl  # noqa: F401

sys.path.insert(0, %r)

from alembic_programmatic import Base, TARGET_METADATA_TABLE  # noqa: E402

config = context.config
target_metadata = Base.metadata


def _include_name(name, type_, parent_names):
    # The demo DB is shared with other recipes; only compare our table so
    # autogenerate never emits drop_table for unrelated tables.
    if type_ == "table":
        return name == TARGET_METADATA_TABLE
    return True


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_name=_include_name,
            include_schemas=False,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
'''


# Minimal script.py.mako so Alembic can render new revision files. Each line is
# a separate tuple element with a trailing comma; the earlier version dropped
# the commas between the four assignment lines, so Python concatenated them into
# one line and the rendered migration was syntactically broken.
_SCRIPT_MAKO_LINES = (
    '"""${message}',
    "",
    "Revision ID: ${up_revision}",
    "Revises: ${down_revision}",
    "Create Date: ${create_date}",
    '"""',
    "from alembic import op",
    "import sqlalchemy as sa",
    "import sqlalchemy_cubrid.types  # noqa: F401",
    "",
    "",
    "revision = ${repr(up_revision)}",
    "down_revision = ${repr(down_revision)}",
    "branch_labels = ${repr(branch_labels)}",
    "depends_on = ${repr(depends_on)}",
    "",
    "",
    "def upgrade() -> None:",
    '    ${upgrades if upgrades else "pass"}',
    "",
    "def downgrade() -> None:",
    '    ${downgrades if downgrades else "pass"}',
)


def _write_migration_scaffold(workdir: Path) -> None:
    """Write env.py + script.py.mako and create the versions/ dir.

    We scaffold the Alembic layout by hand instead of calling
    ``alembic.command.init``: init requires an on-disk ``alembic.ini`` and would
    refuse to write into a directory we already populated.
    """
    migrations_dir = workdir / "migrations"
    versions_dir = migrations_dir / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    # The directory that holds THIS module, so env.py can import it back.
    module_dir = str(Path(__file__).resolve().parent)
    (migrations_dir / "env.py").write_text(_ENV_PY_TEMPLATE % module_dir)
    (migrations_dir / "script.py.mako").write_text("\n".join(_SCRIPT_MAKO_LINES))


def _reset_demo_state() -> None:
    """Drop the demo table and Alembic's bookkeeping table for a clean run."""
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS cookbook_alembic_demo")
        # Alembic records the applied head here; leftover rows from a previous
        # run would point at a revision file the fresh temp dir no longer has.
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    engine.dispose()


def _table_exists() -> bool:
    from sqlalchemy import inspect

    engine = create_engine(DATABASE_URL)
    try:
        return TARGET_METADATA_TABLE in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def main() -> None:
    import alembic.command  # local import: keep top-level importable

    print("=== Alembic Programmatic Migration Demo (CUBRID) ===")
    print()

    workdir = Path(tempfile.mkdtemp(prefix="cookbook_alembic_"))
    print("[1] Created isolated temp working directory")

    _reset_demo_state()
    print(f"[2] Ensured table {TARGET_METADATA_TABLE} does not exist")

    _write_migration_scaffold(workdir)
    cfg = _build_alembic_config(workdir)
    print("[3] Wrote env.py and script.py.mako")

    # Alembic prints nondeterministic details (temp paths, generated revision
    # ids) to stdout; swallow those so this demo's output stays golden-stable.
    # The migration files still contain the real revision id and create date.
    alembic_noise = io.StringIO()

    # ------------------------------------------------------------------
    # Step 4: autogenerate a migration from the ORM metadata. Alembic inspects
    # the live DB schema, compares it against Base.metadata (restricted to our
    # table), and writes a revision file with upgrade()/downgrade() filled in.
    # ------------------------------------------------------------------
    with contextlib.redirect_stdout(alembic_noise):
        alembic.command.revision(
            cfg,
            message="create cookbook_alembic_demo",
            autogenerate=True,
        )
    print("[4] Autogenerated migration revision")

    # Step 5: apply the migration (upgrade head).
    with contextlib.redirect_stdout(alembic_noise):
        alembic.command.upgrade(cfg, "head")
    print("[5] Upgraded to head (table should now exist)")

    if _table_exists():
        print(f"[6] Verified: {TARGET_METADATA_TABLE} now exists in the DB")
    else:
        print(f"[6] WARNING: table {TARGET_METADATA_TABLE} not found after upgrade")

    # Step 7: downgrade one revision (drops the table).
    with contextlib.redirect_stdout(alembic_noise):
        alembic.command.downgrade(cfg, "-1")
    print("[7] Downgraded one revision (table should be dropped)")

    if not _table_exists():
        print(f"[8] Verified: {TARGET_METADATA_TABLE} dropped after downgrade")
    else:
        print("[8] WARNING: table still present after downgrade")

    # Leave the shared database clean for other recipes.
    _reset_demo_state()

    print()
    print("--- CUBRID + Alembic notes ---")
    print("  * CubridImpl is registered by importing sqlalchemy_cubrid.alembic_impl.")
    print("  * transactional_ddl = False  -> each DDL statement auto-commits.")
    print("  * No native SEQUENCE support  -> migrations use AUTO_INCREMENT.")
    print("  * Identifiers are lowercase-folded with a 254-char max.")
    print()
    print("For a real project layout (alembic.ini at repo root), see README.md.")


if __name__ == "__main__":
    main()
