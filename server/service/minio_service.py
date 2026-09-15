from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from minio import Minio, S3Error
import os

load_dotenv()
client = Minio(
    endpoint=os.environ.get("MINIO_HOST"),
    access_key=os.environ.get("MINIO_ROOT_USER"),
    secret_key=os.environ.get("MINIO_ROOT_PASSWORD"),
    secure=False,
)

bucket_name = os.environ.get("MINIO_BUCKET")


def download_inputs_locally(run_id: str, filenames: list[str]) -> None:
    try:
        for filename in filenames:
            object_name = f"jobs/{run_id}/inputs/{filename}"
            input_path = Path("/shared") / run_id / "inputs"
            input_path.mkdir(parents=True, exist_ok=True)
            local_path = input_path / filename
            client.fget_object(bucket_name, object_name, str(local_path))
            print(f"\nDownloaded {object_name} to {local_path}")
    except Exception as e:
        print(f"\nError occurred while downloading input files: {str(e)}")
        raise e


def list_input_files(run_id: str) -> list[str]:
    try:
        prefix = f"jobs/{run_id}/inputs/"
        objects = client.list_objects(bucket_name, prefix=prefix, recursive=True)
        file_list = [obj.object_name.replace(prefix, "") for obj in objects]
        print(f"\nInput files for run_id {run_id}: {file_list}")
        return file_list
    except Exception as e:
        print(f"\nError occurred while listing input files: {str(e)}")
        raise e


def ensure_bucket_exists() -> None:
    try:
        found = client.bucket_exists(bucket_name)
        if not found:
            client.make_bucket(bucket_name)
            print("Created bucket", bucket_name)
        else:
            print("Bucket", bucket_name, "already exists")
    except S3Error as e:
        print("Error occurred while checking/creating bucket:", e)
        raise e


def presign_file_urls(filenames: list[str], run_id: str) -> list[str]:
    try:
        ensure_bucket_exists()
        urls = []
        for filename in filenames:
            try:
                url = client.presigned_put_object(
                    bucket_name,
                    f"jobs/{run_id}/inputs/{filename}",
                    expires=timedelta(minutes=10),
                )
                print(f"\nCreated presigned URL for {filename}:\n{url}")
                urls.append(url)
            except Exception as e:
                print(f"\nError occurred while presigning URL for {filename}: {str(e)}")
        return urls
    except Exception as e:
        print(f"\nError occurred while presigning file URLs: {str(e)}")
        raise e
