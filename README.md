# NL2ETL - POC
> Generate, validate, and self-correct ETL pipelines from natural language.

---

## Functionalities
User describes a data transformation in natural language and uploads source files.

1. **Schema inference** - reads the input file and extracts column names, types and sample values
2. **Plan generation** - maps user intent to exact column names via a schema-aware LLM call
3. **Code generation** - converts the pipeline plan into a Python/Pandas script
4. **AST validation** — scans the generated code for dangerous operations before anything runs
5. **Sandboxed execution** — runs the generated script in an isolated Docker container
6. **Self-correction loop** — if execution fails, feeds the error back to the LLM and retries
7. **Async job tracking** — stores minimal metadata in MinIO so the client can poll status and download outputs

---

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) or Docker Compose on Linux
- [Groq API key](https://console.groq.com)

### 1. Configure environment
Create a `.env` file in the project root with at least:
```bash
GROQ_API_KEY=your_key_here
GROQ_MODEL=openai/gpt-oss-120b
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_HOST=host.docker.internal:9000
MINIO_BUCKET=nl2etl
```

### 2. Run the stack
```bash
docker compose up --build
```

This starts:
- FastAPI backend on http://localhost:8000
- Streamlit client on http://localhost:8501
- MinIO on http://localhost:9000
- Docker sandbox image for isolated execution

### 3. Use the Streamlit client
Open http://localhost:8501 and:
1. Enter the transformation prompt
2. Upload one or more input files
3. Click "Run pipeline"
4. Watch status updates and inspect each attempt in the collapsible sections
5. Download the produced output files from the generated presigned GET URLs

### 4. Server API flow
The backend supports the following flow:
- POST /presign -> returns upload URLs and a run_id
- PUT uploaded files to the returned presigned URLs
- POST /run -> returns 202 Accepted immediately and starts processing in the background
- GET /pipelines/{run_id} -> poll job status and attempts
- POST /presign-get -> returns short-lived download URLs for finished outputs

Example request:
```json
{
  "nl_prompt": "Calculate total revenue by region and export to CSV",
  "run_id": "123e4567-e89b-12d3-a456-426614174000"
}
```
