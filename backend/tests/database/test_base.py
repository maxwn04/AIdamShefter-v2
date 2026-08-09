from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, Table

from backend.database.base import Base


def test_naming_convention_covers_all_schema_objects() -> None:
    parent = Table(
        "parents",
        Base.metadata,
        Column[int]("id", Integer, primary_key=True),
        schema="core",
    )
    child = Table(
        "children",
        Base.metadata,
        Column[int]("id", Integer, primary_key=True),
        Column[int]("parent_id", ForeignKey("core.parents.id"), nullable=False),
        Column[int]("count", Integer, nullable=False),
        CheckConstraint("count >= 0", name="count_non_negative"),
        schema="core",
    )

    names = {constraint.name for constraint in child.constraints}
    assert "pk_children" in names
    assert "fk_children_parent_id_parents" in names
    assert "ck_children_count_non_negative" in names

    Base.metadata.remove(child)
    Base.metadata.remove(parent)
