"""Keep library-owned memory tables out of ORM autogeneration."""

from typing import Any

MEMORY_TABLES = frozenset({"agent_memory", "agent_memory_operations", "agent_memory_metadata"})


def include_migration_object(
    object_: Any, name: str, type_: str, reflected: bool, compare_to: Any
) -> bool:
    return not (type_ == "table" and name in MEMORY_TABLES)
