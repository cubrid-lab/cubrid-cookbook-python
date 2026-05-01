# pyright: reportImplicitRelativeImport=false, reportUnusedParameter=false
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from database import get_db
from models import Task
from schemas import TaskCreate, TaskList, TaskResponse, TaskUpdate

router = APIRouter(prefix="/tasks")


@router.get("", response_model=TaskList)
def list_tasks(
    *,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    completed: Annotated[bool | None, Query()] = None,
    priority: Annotated[int | None, Query(ge=1, le=5)] = None,
    db: Annotated[Session, Depends(get_db)],
) -> TaskList:
    filters: list[ColumnElement[bool]] = []
    if completed is not None:
        filters.append(Task.completed == completed)
    if priority is not None:
        filters.append(Task.priority == priority)

    total_stmt = select(func.count(Task.id))
    if filters:
        total_stmt = total_stmt.where(*filters)
    total = db.scalar(total_stmt) or 0

    stmt = select(Task).order_by(Task.id.desc()).offset(skip).limit(limit)
    if filters:
        stmt = stmt.where(*filters)

    items = [TaskResponse.model_validate(task) for task in db.scalars(stmt).all()]
    return TaskList(items=items, total=total, skip=skip, limit=limit)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, db: Annotated[Session, Depends(get_db)]) -> TaskResponse:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return TaskResponse.model_validate(task)


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Annotated[Session, Depends(get_db)]) -> TaskResponse:
    task = Task(
        title=payload.title,
        description=payload.description,
        completed=1 if payload.completed else 0,
        priority=payload.priority,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return TaskResponse.model_validate(task)


@router.put("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> TaskResponse:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    updates = cast(dict[str, object], payload.model_dump(exclude_unset=True))
    if "completed" in updates:
        updates["completed"] = 1 if updates["completed"] else 0
    for field_name, value in updates.items():
        setattr(task, field_name, value)

    db.add(task)
    db.commit()
    db.refresh(task)
    return TaskResponse.model_validate(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, db: Annotated[Session, Depends(get_db)]) -> Response:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    db.delete(task)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
