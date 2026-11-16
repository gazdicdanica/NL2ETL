import os
import time

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="NL2ETL Studio", page_icon="🧠", layout="wide")

if "job_result" not in st.session_state:
    st.session_state["job_result"] = None
if "job_id" not in st.session_state:
    st.session_state["job_id"] = None


def api_request(method: str, url: str, payload: dict | None = None, timeout: int = 60):
    if method == "GET":
        response = requests.get(url, timeout=timeout)
    elif method == "POST":
        response = requests.post(url, json=payload, timeout=timeout)
    elif method == "PUT":
        response = requests.put(url, data=payload, timeout=timeout)
    else:
        raise ValueError(f"Unsupported method: {method}")

    try:
        data = response.json()
    except ValueError:
        data = {"raw": response.text}

    return response.status_code, data


def upload_files_to_server(files):
    if not files:
        return None

    file_names = [f.name for f in files]
    status, presign_data = api_request(
        "POST",
        f"{API_BASE_URL}/presign",
        {"file_names": file_names},
    )

    if status != 200:
        raise RuntimeError(f"Could not create upload URLs: {presign_data}")

    run_id = presign_data["run_id"]
    uploads = presign_data.get("uploads", [])
    if not uploads:
        raise RuntimeError("No upload URLs returned by the server")

    url_by_name = {entry["filename"]: entry["path"] for entry in uploads}

    for uploaded_file in files:
        put_url = url_by_name.get(uploaded_file.name)
        if not put_url:
            raise RuntimeError(f"No upload URL was returned for {uploaded_file.name}")

        uploaded_file.seek(0)
        put_response = requests.put(put_url, data=uploaded_file.read(), timeout=120)
        if put_response.status_code not in (200, 204):
            raise RuntimeError(
                f"Upload failed for {uploaded_file.name}: {put_response.status_code}"
            )

    return run_id


def poll_job(run_id: str, timeout_seconds: int = 180) -> dict | None:
    deadline = time.time() + timeout_seconds
    last_seen = None

    while time.time() < deadline:
        status_code, payload = api_request("GET", f"{API_BASE_URL}/pipelines/{run_id}")
        if status_code == 200:
            last_seen = payload
            status = payload.get("status", "created")
            if status in {"succeeded", "failed"}:
                return payload
            st.write(f"Status: {status}")
        else:
            last_seen = payload
        time.sleep(2)

    return last_seen


def get_download_url(run_id: str, object_path: str) -> str | None:
    status, payload = api_request(
        "POST",
        f"{API_BASE_URL}/presign-get",
        {"run_id": run_id, "paths": [object_path]},
    )
    if status != 200:
        return None

    gets = payload.get("gets", [])
    if not gets:
        return None

    return gets[0].get("url")


def render_job_result(job_id: str, final_status: dict):
    status = final_status.get("status", "unknown")
    st.subheader(f"Final status: {status}")

    attempts = final_status.get("attempts", [])
    if attempts:
        for attempt in attempts:
            attempt_state = attempt.get("state", "unknown")
            with st.expander(
                f"Attempt {attempt.get('attempt_index', '?')} - {attempt_state}",
                expanded=(attempt_state == "failed"),
            ):
                st.json(attempt)
                script_path = attempt.get("script_path")
                if script_path:
                    script_url = get_download_url(job_id, script_path)
                    if script_url:
                        script_response = requests.get(script_url, timeout=120)
                        script_response.raise_for_status()
                        st.download_button(
                            key=f"script_{job_id}_{attempt.get('attempt_index')}",
                            label=f"Download script for attempt {attempt.get('attempt_index')}",
                            data=script_response.content,
                            file_name=script_path.split("/")[-1],
                            mime="text/x-python",
                        )

    outputs = final_status.get("outputs", [])
    if outputs:
        st.subheader("Outputs")
        for item in outputs:
            object_path = item if isinstance(item, str) else item.get("path")
            filename = object_path.split("/")[-1] if object_path else "download"
            url = get_download_url(job_id, object_path)
            if url:
                response = requests.get(url, timeout=120)
                response.raise_for_status()
                st.download_button(
                    key=f"output_{job_id}_{filename}",
                    label=f"Download {filename}",
                    data=response.content,
                    file_name=filename,
                    mime="application/octet-stream",
                )
            else:
                st.write(f"Could not generate a download URL for {filename}")
    else:
        st.write("No output files were recorded for this run.")

    if status == "failed":
        st.error(final_status.get("error") or "The pipeline finished with an error.")


st.title("NL2ETL Studio")
st.caption(
    "Submit a prompt and upload source files, then track the async pipeline run."
)

with st.form("job_form"):
    prompt = st.text_area(
        "Prompt", height=140, placeholder="Summarize sales by region and export totals"
    )
    files = st.file_uploader("Input files", accept_multiple_files=True)
    submitted = st.form_submit_button("Run pipeline")

if submitted:
    if not prompt.strip():
        st.warning("Please enter a prompt before running.")
    elif not files:
        st.warning("Please upload at least one input file.")
    else:
        with st.spinner("Uploading files and creating the job..."):
            try:
                run_id = upload_files_to_server(files)
                if not run_id:
                    st.error("The upload step did not return a run identifier.")
                    st.stop()
            except Exception as exc:  # pragma: no cover - UI error path
                st.error(f"Upload failed: {exc}")
                st.stop()

        st.success(f"Job created with run_id: {run_id}")

        with st.spinner("Starting the async pipeline run..."):
            status_code, run_payload = api_request(
                "POST",
                f"{API_BASE_URL}/run",
                {"nl_prompt": prompt, "run_id": run_id},
            )

        if status_code not in (200, 202):
            st.error(f"Could not start pipeline: {run_payload}")
            st.stop()

        st.info("The run is in progress. Polling for job status...")
        final_status = poll_job(run_id)

        if not final_status:
            st.error("The job did not finish within the timeout window.")
            st.stop()

        st.session_state["job_id"] = run_id
        st.session_state["job_result"] = final_status

if st.session_state["job_result"] is not None:
    render_job_result(st.session_state["job_id"], st.session_state["job_result"])
