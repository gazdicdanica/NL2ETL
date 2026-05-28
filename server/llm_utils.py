import json
import os

import pandas as pd
from .groq import client
from pathlib import Path

INPUT_DIR = Path(os.environ.get("INPUT_DIR", "/app/input"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


def infer_schema(filename: str) -> dict:

    filepath = INPUT_DIR / filename
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
- Return ONLY the JSON, no explanation
- No extra prose

### Input
"{nl_prompt}"

### Example output
Return only a valid JSON object with following structure:
{{
    "inputs": [
        {{"alias": "df1", "filename": "sales.csv"}}
    ],
    "column_mappings": [
        {{"user_term": "revenue", "resolved_column": "rev", "confidence": "high}}
    ],
    "steps" [
        {{"type": "aggregate", "group_by": "reg", "agg": "sum", "column": "rev", "output_alias": "total_revenue"}}
    ],
    "outputs": [
        {{"filename": "output.xlsx", "format": "excel"}}
    ],
    "ambiguities": []
}}

"""


def _generate_system_role_planning_prompt() -> str:
    return "You are an ETL pipeline planner."


def _generate_system_role_coding_prompt() -> str:
    return "You are an ETL code generator. Generate a Python script using only Pandas."


def generate_plan(nl_prompt: str, schemas: list[dict]) -> dict:
    prompt = _build_planning_prompt(nl_prompt, schemas)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": _generate_system_role_planning_prompt()},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def build_code_prompt(plan: dict, schemas: list[dict]) -> str:
    return f"""
### Pipeline plan:
{json.dumps(plan, indent=2)}

### Execution environment:
- The script runs inside an isolated sandbox container
- The current working directory is the job workspace
- Input files are located in ./input
- Output files must be written to ./output

### Rules:
- Use pathlib.Path for all filesystem paths
- Read all input files ONLY from Path("./input")
- Write all output files ONLY to Path("./output")
- Never use absolute filesystem paths
- Use ONLY pandas, pathlib, and os
- Do NOT use subprocess, eval, exec, requests, socket
- Do NOT access files outside ./input and ./output
- Create output directory if it does not exist
- Print row counts after each major transformation step
- column_mappings in the plan are for reference ONLY — they tell you which column corresponds to which user concept
- column_mappings are NOT to be used for renaming, use actual column names from the schema
- Return ONLY valid executable Python code
- Include:
    if __name__ == "__main__":
        main()
"""


def generate_code(plan: dict, schemas: list[dict]) -> str:
    prompt = build_code_prompt(plan, schemas)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": _generate_system_role_coding_prompt()},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("python"):
            raw = raw[6:]
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()
