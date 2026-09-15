import json
import uuid
from fastapi import FastAPI, Response
from .model.request import PresignRequest, RunPOC

from .service.llm_service import run_pipeline_generation

from .service.minio_service import presign_file_urls as presign

app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.post("/presign", status_code=200)
def presign_file_urls(presign_request: PresignRequest, response: Response) -> dict:
    try:
        run_id = str(uuid.uuid4())
        urls = presign(presign_request.file_names, run_id)

        response.status_code = 200
        return {"message": "Success", "urls": urls, "run_id": run_id}
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")
        response.status_code = 500
        return {"message": "Internal server error", "error": str(e)}


@app.post("/run", status_code=200)
def run_poc(run_poc: RunPOC, response: Response) -> dict:

    try:
        success, stdout, stderr = run_pipeline_generation(
            run_poc.nl_prompt, run_poc.run_id
        )

        if success:
            print(f"\nExecution succeeded. Output files:\n{stdout}")
            response.status_code = 200
            return {"message": "Success", "output_files": stdout.splitlines()}
        else:
            print(f"\nExecution failed with error:\n{stderr}")
            response.status_code = 400
            return {"message": "Execution failed", "error": stderr}
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")
        response.status_code = 500
        return {"message": "Internal server error", "error": str(e)}
