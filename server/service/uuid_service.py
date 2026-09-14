import uuid


def generate_run_id() -> str:
    return str(uuid.uuid4())
