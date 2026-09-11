from uuid import uuid4


def new_id(prefix: str) -> str:
    """Return an opaque, namespaced UUID identifier."""
    return f"{prefix}_{uuid4().hex}"


def is_valid_id(value: str, prefix: str) -> bool:
    """Return whether *value* is a lowercase UUID hex ID for *prefix*."""
    expected = f"{prefix}_"
    suffix = value.removeprefix(expected)
    return value.startswith(expected) and len(suffix) == 32 and all(
        character in "0123456789abcdef" for character in suffix
    )

