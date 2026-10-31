"""Autogenerate filter shared by env.py and the migration test."""

from app.models import Base


def include_object(obj, name, type_, reflected, compare_to):  # noqa: ANN001, ANN201
    # Procrastinate owns its own tables/functions; only compare our tables.
    if type_ == "table" and reflected and compare_to is None:
        return name in Base.metadata.tables
    return True
