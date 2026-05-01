"""03_relationships.py - Parent/child relationships without DB-level cascade.

Demonstrates:
- One-to-many Department -> Employee using relationship()
- Lazy loading and eager loading (selectinload)
- Application-managed child-first deletion order
"""

from __future__ import annotations

from typing import final

from sqlalchemy import ForeignKey, Integer, String, create_engine, select
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    selectinload,
)

DATABASE_URL = "cubrid+pycubrid://dba@localhost:33000/testdb"


class Base(DeclarativeBase):
    pass


@final
class Department(Base):
    __tablename__ = "cookbook_departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dept_name: Mapped[str] = mapped_column(String(80), unique=True)
    employees: Mapped[list[Employee]] = relationship(back_populates="department")


@final
class Employee(Base):
    __tablename__ = "cookbook_employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_name: Mapped[str] = mapped_column(String(80))
    active_flag: Mapped[int] = mapped_column(Integer, default=1)
    department_id: Mapped[int] = mapped_column(ForeignKey("cookbook_departments.id"))
    department: Mapped[Department] = relationship(back_populates="employees")


def main() -> None:
    engine = create_engine(DATABASE_URL)
    print("=== ORM Relationships (Department / Employee) ===")

    try:
        print("[1] Creating tables")
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            print("\n[2] Seeding parent/child rows")
            engineering = Department(dept_name="Engineering")
            support = Department(dept_name="Support")
            session.add_all(
                [
                    engineering,
                    support,
                    Employee(employee_name="Alice", active_flag=1, department=engineering),
                    Employee(employee_name="Bob", active_flag=1, department=engineering),
                    Employee(employee_name="Eun", active_flag=0, department=support),
                ]
            )
            session.commit()
            print("Seed complete")

            print("\n[3] Lazy loading: access department.employees")
            departments = session.scalars(select(Department).order_by(Department.id)).all()
            for department in departments:
                names = [employee.employee_name for employee in department.employees]
                print(f"{department.dept_name}: {names}")

            print("\n[4] Eager loading with selectinload")
            eager_departments = session.scalars(
                select(Department)
                .options(selectinload(Department.employees))
                .order_by(Department.id)
            ).all()
            for department in eager_departments:
                names = [employee.employee_name for employee in department.employees]
                print(f"{department.dept_name} (eager): {names}")

            print("\n[5] Child-first deletion (no DB-level CASCADE)")
            employees = session.scalars(select(Employee)).all()
            for employee in employees:
                session.delete(employee)
            session.commit()
            print(f"Deleted {len(employees)} child rows from cookbook_employees")

            departments = session.scalars(select(Department)).all()
            for department in departments:
                session.delete(department)
            session.commit()
            print(f"Deleted {len(departments)} parent rows from cookbook_departments")

        print("\nRelationship demo completed.")
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
        print("Cleanup complete.")


if __name__ == "__main__":
    main()
