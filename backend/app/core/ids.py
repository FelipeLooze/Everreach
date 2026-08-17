from uuid import uuid4


def generate_id(prefix: str) -> str:
    """Generate a prefixed unique id, e.g. 'npc_3f9a2b1c4d5e'.

    Every important entity must be referenced by id, never by name alone.
    """
    return f"{prefix}_{uuid4().hex[:12]}"
