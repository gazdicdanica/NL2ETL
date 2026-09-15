from pathlib import Path
import os
import time
import docker

SANDBOX_IMAGE = os.environ.get("SANDBOX_IMAGE", "nl2etl_sandbox")

client = docker.from_env()


def execute_in_docker(code: str, run_id: str) -> tuple[bool, str, str]:

    workdir = Path("/shared") / run_id
    output_path = workdir / "outputs"
    output_path.mkdir(parents=True, exist_ok=True)

    # write script
    script_path = workdir / "pipeline.py"
    script_path.write_text(code, encoding="utf-8")
    os.sync()
    time.sleep(0.3)
    # run container
    container = client.containers.run(
        image=SANDBOX_IMAGE,
        command="python pipeline.py",
        working_dir=f"/shared/{run_id}",
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

    # if success:
    #     # Save the output files locally
    #     OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    #     for f in output_path.iterdir():
    #         shutil.copy(f, OUTPUT_DIR / f"{run_id}_{f.name}")

    #     # Save the generated pipeline script locally
    #     SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    #     script_dest = SCRIPTS_DIR / f"{run_id}_pipeline.py"
    #     shutil.copy(script_path, script_dest)

    # # Cleanup the temporary job directory from shared volume
    # shutil.rmtree(workdir, ignore_errors=True)

    return success, stdout, stderr
