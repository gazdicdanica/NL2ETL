import json
import os
import shutil
from typing import Any

import pandas as pd

from ..validator.ast_validator import validate_code
from ..groq import client
from .execution_service import execute_in_docker
from pathlib import Path
from .minio_service import (
    list_input_files,
    download_inputs_locally,
    upload_output_files,
)

# INPUT_DIR = Path(os.environ.get("INPUT_DIR", "/app/input"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
GROQ_MODEL = os.environ.get("GROQ_MODEL")


def run_pipeline_generation(user_prompt: str, run_id: str) -> tuple[bool, str, str]:
    # success, stdout, stderr
    input_files = list_input_files(run_id)
    download_inputs_locally(run_id, input_files)
    schemas = [infer_schema(f, run_id) for f in input_files]
    print(f"Schemas inferred: {[s['filename'] for s in schemas]}")

    plan = generate_plan(user_prompt, schemas)
    print(f"Pipeline plan:\n{json.dumps(plan, indent=2)}")

    if plan.get("ambiguities"):
        print(f"\nAmbiguities detected: {plan['ambiguities']}")
        return  # In full system: show UI disambiguation prompt

    return generate_correct_script(user_prompt, plan, schemas, run_id)


def infer_schema(filename: str, run_id: str) -> dict:
    filepath = Path("/shared") / run_id / "inputs" / filename
    df = pd.read_csv(filepath)

    return {
        "filename": filename,
        "columns": [
            {
                "name": col,
                "dtype": str(df[col].dtype),
                "sample_values": df[col].dropna().head(n=3).tolist(),
            }
            for col in df.columns
        ],
        "row_count": len(df),
    }


def _build_schema_str(schemas: list[dict]) -> str:
    schema_str = ""
    for schema in schemas:
        schema_str += f"\nFile: {schema['filename']}\nColumns:\n"
        for col in schema["columns"]:
            schema_str += (
                f"   - {col['name']} {col['dtype']}  e.g. {col['sample_values']}\n"
            )

    return schema_str


def _build_planning_prompt(nl_prompt: str, schemas: list[dict]) -> str:
    schema_str = _build_schema_str(schemas)

    return f"""
### Context
The user has these datasources available:
{schema_str}

### Instructions
- use EXACT column names from the schema above
- Map user terms to actual column names in column_mappings
- If unsure about a column mapping add it to ambiguities
- Return ONLY the JSON, no explanation. Do not wrap it in quotes. Do not use markdown.
- No extra prose

### Input
{nl_prompt}

### Example output
Return only a valid JSON object with following structure:
{{
    "inputs": [
        {{"alias": "df1", "filename": "sales.csv"}}
    ],
    "column_mappings": [
        {{"user_term": "revenue", "resolved_column": "rev", "confidence": "high"}}
    ],
    "steps": [
        {{"type": "aggregate", "group_by": "reg", "agg": "sum", "column": "rev", "output_alias": "total_revenue"}}
    ],
    "outputs": [
        {{"filename": "output.xlsx", "format": "excel"}}
    ],
    "ambiguities": []
}}

"""


def generate_plan(nl_prompt: str, schemas: list[dict]) -> dict:
    prompt = _build_planning_prompt(nl_prompt, schemas)
    return json.loads(send_request("You are an ETL pipeline planner.", prompt))


def _build_code_prompt(plan: dict, run_id: str) -> str:
    return f"""
### Pipeline plan:
{json.dumps(plan, indent=2)}

### Execution environment:
- The script runs inside an isolated sandbox container
- The current working directory is /shared/{run_id}
- Input files are located in ./inputs
- Output files must be written to ./outputs

### Rules:
- Use pathlib.Path for all filesystem paths
- Read all input files ONLY from Path("./inputs")
- Write all output files ONLY to Path("./outputs")
- Name output files exactly as specified in the plan
- Never use absolute filesystem paths
- Use ONLY pandas, pathlib, and os
- Do NOT use subprocess, eval, exec, requests, socket
- Do NOT access files outside /shared/{run_id}
- Print row counts after each major transformation step
- column_mappings in the plan are for reference ONLY — they tell you which column corresponds to which user concept
- column_mappings are NOT to be used for renaming, use actual column names from the schema
- Return ONLY valid executable Python code
- Include:
    if __name__ == "__main__":
        main()
"""


def generate_code(plan: dict, run_id: str) -> str:
    prompt = _build_code_prompt(plan, run_id)
    return send_request("You are an ETL code generator.", prompt)


# # Test hook for self-correction: first generation returns a code snippet with a deliberate runtime error.
# call_count = 0
# original_generate_code = generate_code

# def generate_code_with_error(plan, schemas):
#     global call_count
#     call_count += 1
#     if call_count == 1:
#         return """
# import pandas as pd
# from pathlib import Path

# def main():
#     df1 = pd.read_csv(Path("./input/sales.csv"))
#     df2 = df1[df1["non_existent_column"].notna()]  # This will cause a KeyError since the column doesn't exist
#     df2.to_csv(Path("./output/total_revenue.csv"), index=False)

# if __name__ == "__main__":
#     main()
# """
#     return original_generate_code(plan, schemas)


# generate_code = generate_code_with_error


def generate_correct_script(
    nl_prompt: str, plan: dict, schemas: list[dict], run_id: str
) -> tuple[bool, str, str]:
    code = generate_code(plan, run_id)

    success, stdout, stderr = self_correction_loop(
        nl_prompt, plan, code, "Initial generation", schemas, run_id
    )

    if success:
        print(f"\nCorrected code executed successfully. Output:\n{stdout}")
    else:
        print(f"\nSelf-correction attempts exhausted. Last error:\n{stderr}")

    return success, stdout, stderr


def _build_correction_prompt(
    nl_prompt: str,
    plan: dict,
    failing_code: str,
    error_message: str,
    schemas: list[dict],
) -> str:
    return f"""### Context
The following code was generated based on the NL prompt and plan, but it failed validation or execution.

### NL prompt:
{nl_prompt}

### Pipeline plan:
{json.dumps(plan, indent=2)}

### Failing code:
{failing_code}

### Error message:
{error_message}

### Available schemas:
{json.dumps([s['columns'] for s in schemas], indent=2)}

### Instructions
- Analyze the error message and any AST validation violations to identify the root cause
- Fix the code so it is valid, safe, and executable
- Return ONLY the corrected code, no explanations or comments
"""


def self_correction_loop(
    nl_prompt: str,
    plan: dict,
    failing_code: str,
    error_message: str,
    schemas: list[dict],
    run_id: str,
    max_iterations: int = 4,
) -> tuple[bool, str, str]:
    success, stdout, stderr = False, "", ""
    current_code = failing_code
    current_error = error_message

    for i in range(max_iterations):
        print(f"Code-generation attempt {i+1}/{max_iterations}")

        valid, violations = validate_code(current_code)
        if not valid:
            violation_text = (
                "; ".join(violations) if violations else "unknown validation issue"
            )
            print(f"AST validation failed with violations:\n{violations}")
            current_error = f"AST validation failed: {violation_text}"
            correction_prompt = _build_correction_prompt(
                nl_prompt, plan, current_code, current_error, schemas
            )
            current_code = send_request(
                "You are an ETL code debugger and fixer", correction_prompt
            )
            continue
        success, stdout, stderr = execute_in_docker(current_code, run_id)

        if success:
            print(f"Code executed successfully on attempt {i+1}")

            # Save the output files to MinIO
            local_path = Path("/shared") / run_id
            minio_path = f"jobs/{run_id}"
            upload_output_files(
                f"{local_path}/outputs", f"{minio_path}/outputs", run_id
            )
            upload_output_files(local_path, f"{minio_path}/scripts", run_id)

            # cleanup
            shutil.rmtree(local_path, ignore_errors=True)
            return success, stdout, stderr

        print(f"Execution failed with error:\n{stderr}")
        current_error = stderr
        correction_prompt = _build_correction_prompt(
            nl_prompt, plan, current_code, current_error, schemas
        )
        current_code = send_request(
            "You are an ETL code debugger and fixer", correction_prompt
        )
    # TODO after max iterations, save the last failing code and error message to MinIO for further analysis.
    print(
        "Max self-correction attempts reached. Returning last attempt's code and error."
    )
    return success, stdout, stderr


def send_request(system_prompt: str, user_prompt: str) -> Any:
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("python"):
            raw = raw[6:]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()
