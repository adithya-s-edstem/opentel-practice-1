"""Data-access layer for todos.

Routes are HTTP adapters; this module is where the SQLAlchemy lives. Keeping
it separate means the CRUD functions are unit-testable without spinning up
Flask, and routes stay tiny.

Uses SQLAlchemy 2.0 `select(...)` style — the legacy `Todo.query.…` API
still works but emits a DeprecationWarning and will go away in a future
major release.
"""

from typing import Optional

from sqlalchemy import select

from extensions import db
from models import Todo


def list_todos() -> list[Todo]:
    stmt = select(Todo).order_by(
        Todo.due_date.is_(None),
        Todo.due_date.asc(),
        Todo.created_at.asc(),
    )
    return list(db.session.execute(stmt).scalars())


def get_todo(todo_id: int) -> Optional[Todo]:
    return db.session.get(Todo, todo_id)


def create_todo(data: dict) -> Todo:
    todo = Todo(**data)
    db.session.add(todo)
    db.session.commit()
    return todo


def update_todo(todo: Todo, patch: dict) -> Todo:
    for key, value in patch.items():
        setattr(todo, key, value)
    db.session.commit()
    return todo


def delete_todo(todo: Todo) -> None:
    db.session.delete(todo)
    db.session.commit()
