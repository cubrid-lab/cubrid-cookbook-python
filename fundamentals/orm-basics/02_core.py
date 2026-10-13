"""02_core.py — SQLAlchemy Core usage with CUBRID.

Demonstrates:
- Table definitions
- Core INSERT, SELECT, UPDATE, DELETE
- text() for raw SQL
- Joins, subqueries, and aggregation
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Double,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    func,
    insert,
    select,
    text,
    update,
)

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"


def get_engine():
    return create_engine(DATABASE_URL)


# Define tables using Core API
metadata = MetaData()

departments = Table(
    "cookbook_core_departments",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False),
    Column("budget", Double, default=0.0),
)

employees = Table(
    "cookbook_core_employees",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False),
    Column("email", String(200), unique=True),
    Column("salary", Double, default=0.0),
    Column("dept_id", Integer),
)


def create_tables(engine) -> None:
    """Create tables from metadata."""
    print("=== Create Tables ===")
    metadata.drop_all(engine)
    metadata.create_all(engine)
    print("  ✓ Created tables: cookbook_core_departments, cookbook_core_employees")


def insert_data(engine) -> None:
    """INSERT — add rows using Core API."""
    print("\n=== Core INSERT ===")

    with engine.begin() as conn:
        # Single insert
        conn.execute(insert(departments).values(name="Engineering", budget=500000.0))
        conn.execute(insert(departments).values(name="Marketing", budget=200000.0))
        conn.execute(insert(departments).values(name="Sales", budget=300000.0))
        print("  ✓ Inserted 3 departments")

        # Batch insert
        conn.execute(
            insert(employees),
            [
                {
                    "name": "Alice",
                    "email": "alice@company.com",
                    "salary": 95000,
                    "dept_id": 1,
                },
                {
                    "name": "Bob",
                    "email": "bob@company.com",
                    "salary": 85000,
                    "dept_id": 1,
                },
                {
                    "name": "Charlie",
                    "email": "charlie@company.com",
                    "salary": 75000,
                    "dept_id": 2,
                },
                {
                    "name": "Diana",
                    "email": "diana@company.com",
                    "salary": 90000,
                    "dept_id": 2,
                },
                {
                    "name": "Eve",
                    "email": "eve@company.com",
                    "salary": 80000,
                    "dept_id": 3,
                },
            ],
        )
        print("  ✓ Inserted 5 employees")


def select_basic(engine) -> None:
    """SELECT — basic queries."""
    print("\n=== Core SELECT ===")

    with engine.connect() as conn:
        # Select all
        result = conn.execute(select(employees).order_by(employees.c.id))
        print("  All employees:")
        for row in result:
            print(f"    {row.id}: {row.name:10s}  {row.email:25s}  ${row.salary:,.0f}")

        # Select with filter
        stmt = (
            select(employees).where(employees.c.salary >= 85000).order_by(employees.c.salary.desc())
        )
        result = conn.execute(stmt)
        print("\n  High earners (>= $85k):")
        for row in result:
            print(f"    {row.name:10s}  ${row.salary:,.0f}")


def select_with_join(engine) -> None:
    """SELECT with JOIN."""
    print("\n=== Core JOIN ===")

    with engine.connect() as conn:
        stmt = (
            select(
                employees.c.name.label("employee"),
                departments.c.name.label("department"),
                employees.c.salary,
            )
            .select_from(employees.join(departments, employees.c.dept_id == departments.c.id))
            .order_by(employees.c.name)
        )
        result = conn.execute(stmt)

        print(f"  {'Employee':12s}  {'Department':15s}  {'Salary':>10s}")
        print(f"  {'--------':12s}  {'----------':15s}  {'------':>10s}")
        for row in result:
            print(f"  {row.employee:12s}  {row.department:15s}  ${row.salary:>9,.0f}")


def aggregation(engine) -> None:
    """Aggregation queries."""
    print("\n=== Core Aggregation ===")

    with engine.connect() as conn:
        stmt = (
            select(
                departments.c.name,
                func.count(employees.c.id).label("headcount"),
                func.avg(employees.c.salary).label("avg_salary"),
                func.sum(employees.c.salary).label("total_salary"),
            )
            .select_from(departments.outerjoin(employees, departments.c.id == employees.c.dept_id))
            .group_by(departments.c.name)
            .order_by(func.count(employees.c.id).desc())
        )
        result = conn.execute(stmt)

        print(f"  {'Department':15s}  {'Count':>5s}  {'Avg Salary':>12s}  {'Total':>12s}")
        print(f"  {'----------':15s}  {'-----':>5s}  {'----------':>12s}  {'-----':>12s}")
        for row in result:
            avg = row.avg_salary or 0
            total = row.total_salary or 0
            print(f"  {row.name:15s}  {row.headcount:5d}  ${avg:>11,.0f}  ${total:>11,.0f}")


def raw_sql(engine) -> None:
    """text() for raw SQL queries."""
    print("\n=== Raw SQL with text() ===")

    with engine.connect() as conn:
        # Simple text query
        result = conn.execute(text("SELECT COUNT(*) FROM cookbook_core_employees"))
        print(f"  Total employees: {result.scalar()}")

        # Parameterized text query
        result = conn.execute(
            text(
                "SELECT name, salary FROM cookbook_core_employees WHERE salary > :min_salary ORDER BY salary DESC"
            ),
            {"min_salary": 80000},
        )
        print("  Employees with salary > $80k:")
        for row in result:
            print(f"    {row[0]:10s}  ${row[1]:,.0f}")


def update_and_delete(engine) -> None:
    """UPDATE and DELETE."""
    print("\n=== Core UPDATE & DELETE ===")

    with engine.begin() as conn:
        # Update
        stmt = (
            update(employees)
            .where(employees.c.dept_id == 1)
            .values(salary=employees.c.salary * 1.1)
        )
        result = conn.execute(stmt)
        print(f"  ✓ Gave Engineering 10% raise ({result.rowcount} rows)")

        # Verify
        stmt = select(employees.c.name, employees.c.salary).where(employees.c.dept_id == 1)
        result = conn.execute(stmt)
        for row in result:
            print(f"    {row.name:10s}  ${row.salary:,.0f}")


def cleanup(engine) -> None:
    metadata.drop_all(engine)
    print("\n✓ Cleaned up")


if __name__ == "__main__":
    engine = get_engine()

    try:
        create_tables(engine)
        insert_data(engine)
        select_basic(engine)
        select_with_join(engine)
        aggregation(engine)
        raw_sql(engine)
        update_and_delete(engine)
    finally:
        cleanup(engine)
        engine.dispose()
