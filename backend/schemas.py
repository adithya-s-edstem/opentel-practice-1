"""Pydantic v2 schemas for request validation.

Pydantic handles type coercion, ISO-8601 parsing (including the trailing 'Z'),
and produces a structured error list which `routes.py` returns as JSON. This
replaces the ad-hoc `data.get(...) or ""` + `abort(400, description=...)`
pattern that the pre-refactor code used.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _strip(v):
    return v.strip() if isinstance(v, str) else v


class TodoCreate(BaseModel):
    """Validated payload for POST /api/todos.

    `title` is stripped before length is checked, so a payload of "   " is
    rejected as empty (mirrors the pre-refactor handler's behaviour).
    """

    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    due_date: Optional[datetime] = None
    completed: bool = False

    _strip_strings = field_validator("title", "description", mode="before")(_strip)

    model_config = ConfigDict(extra="ignore")


class TodoUpdate(BaseModel):
    """Validated payload for PUT /api/todos/<id>.

    All fields optional — the route applies only the keys that were actually
    present in the request via `model_dump(exclude_unset=True)`. An explicit
    `{"title": null}` is rejected (would otherwise hit the DB NOT NULL
    constraint at commit time).
    """

    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    completed: Optional[bool] = None

    _strip_strings = field_validator("title", "description", mode="before")(_strip)

    @model_validator(mode="after")
    def _reject_null_title(self):
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title cannot be null")
        return self

    model_config = ConfigDict(extra="ignore")
