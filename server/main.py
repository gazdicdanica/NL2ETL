import json
from fastapi import FastAPI, Response

from .model.request import RunPOC

from .utils.llm_utils import infer_schema, generate_plan, generate_correct_script

app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.post("/", status_code=200)
def run_poc(run_poc: RunPOC, response: Response) -> dict:

    try:
        schemas = [infer_schema(f) for f in run_poc.input_files]
        print(f"Schemas inferred: {[s['filename'] for s in schemas]}")

        plan = generate_plan(run_poc.nl_prompt, schemas)
        print(f"Pipeline plan:\n{json.dumps(plan, indent=2)}")

        if plan.get("ambiguities"):
            print(f"\nAmbiguities detected: {plan['ambiguities']}")
            return  # In full system: show UI disambiguation prompt

        success, stdout, stderr = generate_correct_script(
            run_poc.nl_prompt, plan, schemas, run_poc.input_files
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
