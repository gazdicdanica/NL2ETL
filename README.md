# NL2ETL - POC
> Generate, validate, and self-correct ETL pipelines from natural language.

---

## Functionalities
User describes data transformation in natural language and includes the input files.

1. **Schema inference** - reads the input file and extracts column names, types and sample values
2. **Plan generation** - maps the users intebt to exact column names via a schema-aware LLM call, returning a structured JSON pipeline plan
3. **Code generation** - converts the JSON plan into a Python/Pandas script
4. **AST validation** — scans the generated code for dangerous operations before anything runs
5. **Sandboxed execution** — runs the generated script in an isolated Docker container
6. **Self-correction loop** — if execution fails, feeds the error back to the LLM and retries (up to N=3 times)

---

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker + Docker Compose on Linux)
- [Groq API key](https://console.groq.com) => free

### 1. Configure environment
Add your GROQ_API_KEY to the `.env` file in the root folder

### 2. Upload input file
Drop a CSV or Excel file into the `input/` folder 

### 3. Run
```bash
docker compose up --build
```

### 4. Execute
The server exposes a POST endpoint at:
```
POST http://localhost:8000
```

**Request body:**
```json
{
  "prompt": "Calculate total revenue by region and export to Excel",
  "files": ["sales.csv"]
}
```
  - `prompt` - data transformation descritpion 
  - `files` - list of filenames from the `input/` folder to use as the ETL input

