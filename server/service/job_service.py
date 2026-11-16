from datetime import datetime
import time
import uuid

from . import minio_service


def _now_iso():
    return datetime.utcnow().isoformat() + "Z"


def create_run_meta(run_id: str | None = None) -> dict:
    if run_id is None:
        run_id = str(uuid.uuid4())
    meta = {
        "run_id": run_id,
        "status": "created",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "attempts": [],
        "outputs": [],
    }
    minio_service.write_meta_json(run_id, meta)
    return meta


def read_meta(run_id: str) -> dict | None:
    return minio_service.read_meta_json(run_id)


def update_meta(run_id: str, patch: dict) -> dict:
    """Read-modify-write with retries. patch is merged into top-level meta."""
    for _ in range(3):
        meta = read_meta(run_id) or {}
        meta.update(patch)
        meta["updated_at"] = _now_iso()
        minio_service.write_meta_json(run_id, meta)
        return meta
    raise RuntimeError("Failed to update meta after retries")


def append_attempt(run_id: str, attempt_record: dict) -> dict:
    for _ in range(3):
        meta = read_meta(run_id) or {}
        attempts = meta.get("attempts", [])
        attempts.append(attempt_record)
        meta["attempts"] = attempts
        meta["updated_at"] = _now_iso()
        minio_service.write_meta_json(run_id, meta)
        return meta
    raise RuntimeError("Failed to append attempt to meta")


def add_output(run_id: str, output_record: dict) -> dict:
    for _ in range(3):
        meta = read_meta(run_id) or {}
        outputs = meta.get("outputs", [])
        outputs.append(output_record)
        meta["outputs"] = outputs
        meta["updated_at"] = _now_iso()
        minio_service.write_meta_json(run_id, meta)
        return meta
    raise RuntimeError("Failed to add output to meta")


def set_status(run_id: str, status: str) -> dict:
    return update_meta(run_id, {"status": status})
