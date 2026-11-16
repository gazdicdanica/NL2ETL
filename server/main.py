import json
import uuid
from fastapi import FastAPI, Response, HTTPException
from .model.request import PresignRequest, RunPOC

from .service.llm_service import run_pipeline_generation
from .service import job_service
from .service.minio_service import presign_file_urls as presign, presigned_get_object

from concurrent.futures import ThreadPoolExecutor

app = FastAPI()

# Simple in-process executor for background runs (MVP)
executor = ThreadPoolExecutor(max_workers=2)


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.post("/presign", status_code=200)
def presign_file_urls(presign_request: PresignRequest, response: Response) -> dict:
    try:
        run_id = str(uuid.uuid4())
        urls = presign(presign_request.file_names, run_id)

        response.status_code = 200
        return {"message": "Success", "uploads": urls, "run_id": run_id}
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")
        response.status_code = 500
        return {"message": "Internal server error", "error": str(e)}


@app.post("/run", status_code=200)
def run_poc(run_poc: RunPOC, response: Response) -> dict:
    try:
        run_id = run_poc.run_id or str(uuid.uuid4())

        # Ensure meta exists
        existing = job_service.read_meta(run_id)
        if not existing:
            job_service.create_run_meta(run_id)

        # Schedule background execution
        def _background():
            try:
                job_service.set_status(run_id, "running")
                success, _, stderr = run_pipeline_generation(run_poc.nl_prompt, run_id)

                if success:
                    job_service.set_status(run_id, "succeeded")
                else:
                    job_service.set_status(run_id, "failed")
            except Exception as exc:
                print(f"Error in background run for {run_id}: {exc}")
                try:
                    job_service.set_status(run_id, "failed")
                except Exception:
                    pass

        executor.submit(_background)

        response.status_code = 202
        return {"message": "Accepted", "run_id": run_id}
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")
        response.status_code = 500
        return {"message": "Internal server error", "error": str(e)}


@app.get("/pipelines/{run_id}")
def get_pipeline_status(run_id: str):
    meta = job_service.read_meta(run_id)
    if not meta:
        raise HTTPException(status_code=404, detail="run_id not found")
    return meta


@app.post("/presign-get")
def presign_get(payload: dict, response: Response):
    try:
        run_id = payload.get("run_id")
        paths = payload.get("paths", [])
        if not run_id or not paths:
            response.status_code = 400
            return {"message": "run_id and paths are required"}

        urls = []
        for p in paths:
            # if p looks like a relative filename, prefix with jobs/{run_id}/outputs/
            if not p.startswith("jobs/"):
                object_name = f"jobs/{run_id}/outputs/{p}"
            else:
                object_name = p
            url = presigned_get_object(object_name)
            urls.append({"path": object_name, "url": url})

        return {"message": "Success", "gets": urls}
    except Exception as e:
        print(f"\nUnexpected error in presign-get: {e}")
        response.status_code = 500
        return {"message": "Internal server error", "error": str(e)}
