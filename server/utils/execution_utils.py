from pathlib import Path
import os
import shutil
import time
import docker
import uuid

INPUT_DIR = Path(os.environ.get("INPUT_DIR", "/app/input"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
SCRIPTS_DIR = Path(os.environ.get("SCRIPTS_DIR", "/app/scripts"))
SANDBOX_IMAGE = os.environ.get("SANDBOX_IMAGE", "nl2etl_sandbox")

client = docker.from_env()


def execute_in_docker(code: str, input_files: list[str]):

    job_id = str(uuid.uuid4())

    workdir = Path("/shared") / job_id
    input_path = workdir / "input"
    output_path = workdir / "output"

    input_path.mkdir(parents=True, exist_ok=True)
    output_path.mkdir(parents=True, exist_ok=True)

    # copy inputs
    for f in input_files:
        source_path = Path(f)
        if not source_path.is_absolute():
            source_path = INPUT_DIR / f

        if not source_path.exists():
            raise FileNotFoundError(f"Input file not found: {source_path}")

        shutil.copy(source_path, input_path / source_path.name)

    # write script
    script_path = workdir / "pipeline.py"
    script_path.write_text(code, encoding="utf-8")
    os.sync()
    time.sleep(0.3)
    # run container
    container = client.containers.run(
        image=SANDBOX_IMAGE,
        command="python pipeline.py",
        working_dir=f"/shared/{job_id}",
        volumes={
            "shared_data": {
                "bind": "/shared",
                "mode": "rw",
            }
        },
        network_disabled=True,
        mem_limit="512m",
        detach=True,
    )

    result = container.wait()
    stdout = container.logs(stdout=True, stderr=False).decode()
    stderr = container.logs(stdout=False, stderr=True).decode()
    success = result["StatusCode"] == 0

    container.remove()

    if success:
        # Save the output files locally
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        for f in output_path.iterdir():
            shutil.copy(f, OUTPUT_DIR / f"{job_id}_{f.name}")

        # Save the generated pipeline script locally
        SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        script_dest = SCRIPTS_DIR / f"{job_id}_pipeline.py"
        shutil.copy(script_path, script_dest)

    # Cleanup the temporary job directory from shared volume
    shutil.rmtree(workdir, ignore_errors=True)

    return success, stdout, stderr
