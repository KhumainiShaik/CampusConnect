#!/usr/bin/env python3
r"""Recreate the storage-enabled Phase 1 deployment before starting Phase 2.

Windows CMD: py scripts\restore_phase1.py --project YOUR_PROJECT_ID
Cloud Shell: python3 scripts/restore_phase1.py --project YOUR_PROJECT_ID

Requires Python 3.10+, authenticated Google Cloud CLI and a running Linux Docker
engine. Uses the standard library only. Run from the workshop-storage source
stage (or its CI/CD successor). The project and billing link must already exist.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
NAME = "campusconnect"
APIS = (
    "run.googleapis.com", "artifactregistry.googleapis.com",
    "storage.googleapis.com", "iam.googleapis.com",
    "logging.googleapis.com", "monitoring.googleapis.com",
)


def run(command, capture=False):
    """Keep commands as argument lists; never interpret them as shell code."""
    result = subprocess.run(
        [str(part) for part in command], check=True,
        stdout=subprocess.PIPE if capture else None,
        text=True, encoding="utf-8", errors="replace",
    )
    return result.stdout.strip() if capture else ""


def gcloud_command():
    executable = shutil.which("gcloud")
    if not executable:
        raise RuntimeError("Install Google Cloud CLI, reopen the terminal and run gcloud auth login.")
    if os.name == "nt" and Path(executable).suffix.lower() in (".cmd", ".bat"):
        # Bypass cmd.exe parsing. The standard Windows SDK ships this entrypoint.
        sdk = Path(executable).resolve().parent.parent
        entry = sdk / "lib" / "gcloud.py"
        bundled_python = sdk / "platform" / "bundledpython" / "python.exe"
        if not entry.is_file():
            raise RuntimeError("Cannot locate Google Cloud CLI's lib/gcloud.py. Use the standard SDK installation or Cloud Shell.")
        interpreter = str(bundled_python) if bundled_python.is_file() else sys.executable
        return [interpreter, str(entry)]
    return [executable]


def verify_service(url, timeout):
    """Check storage routes as well as process health; allow IAM propagation."""
    deadline = time.monotonic() + timeout
    routes = ("/health", "/", "/api/events", "/resources/announcement.txt", "/resources/poster.svg")
    while True:
        try:
            for route in routes:
                with urlopen(url + route, timeout=20) as response:
                    body = response.read()
                    if response.status != 200 or not body:
                        raise ValueError(f"{route}: expected a nonempty HTTP 200 response")
                    if route == "/health" and json.loads(body) != {"status": "ok"}:
                        raise ValueError("Health response is not ok")
                    if route == "/" and b"CampusConnect" not in body:
                        raise ValueError("Homepage does not contain CampusConnect")
                    if route == "/api/events" and not isinstance(json.loads(body), list):
                        raise ValueError("Events API did not return a list")
                    if route.endswith("poster.svg") and "<svg" not in body.decode("utf-8"):
                        raise ValueError("Poster response is not SVG")
            return
        except (URLError, TimeoutError, OSError, ValueError) as error:
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"Deployment exists at {url}, but verification failed: {error}. "
                    "Inspect Cloud Run Logs, runtime identity and bucket permissions; then rerun."
                ) from error
            print(f"Waiting for application access: {error}. Retrying in 10 seconds...", flush=True)
            time.sleep(10)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", required=True, help="Existing billing-enabled Google Cloud project ID")
    parser.add_argument("--region", default="asia-south1")
    parser.add_argument("--bucket", help="Bucket name without gs://; default: PROJECT-campusconnect-assets")
    parser.add_argument("--verify-timeout", type=int, default=180, help="Seconds to retry live checks (default: 180)")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", args.project):
        parser.error("--project must be a project ID, not a project name or number")
    if not re.fullmatch(r"[a-z]+-[a-z]+[0-9]+", args.region):
        parser.error("--region must be a region such as asia-south1")
    bucket = args.bucket or f"{args.project}-campusconnect-assets"
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,61}[a-z0-9]", bucket):
        parser.error("Use a 3-63 character bucket name containing lowercase letters, numbers, hyphens or underscores")
    if args.verify_timeout < 1:
        parser.error("--verify-timeout must be positive")

    print("1/7 Checking tools, storage application source and Google account", flush=True)
    for relative in ("app.py", "requirements.txt", "Dockerfile.optimised", "templates/index.html",
                     "sample-assets/announcement.txt", "sample-assets/poster.svg"):
        if not (ROOT / relative).is_file():
            raise RuntimeError(f"Missing {relative}. Use the complete workshop-storage source branch.")
    if "google-cloud-storage" not in (ROOT / "requirements.txt").read_text(encoding="utf-8"):
        raise RuntimeError("The selected source is not the storage application. Switch to workshop-storage.")
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("Install/start Docker Desktop with Linux containers, or use Cloud Shell.")
    if run([docker, "info", "--format", "{{.OSType}}"], capture=True) != "linux":
        raise RuntimeError("Docker must be running in Linux containers mode.")
    gcloud = gcloud_command()
    impersonation = run(gcloud + ["config", "get-value", "auth/impersonate_service_account"], capture=True)
    if impersonation not in ("", "(unset)"):
        raise RuntimeError("Use a gcloud configuration signed in as the deploying user, without service-account impersonation.")
    accounts = json.loads(run(gcloud + ["auth", "list", "--filter=status:ACTIVE", "--format=json"], capture=True))
    if len(accounts) != 1:
        raise RuntimeError("Run gcloud auth login and select the project-owning Google account before retrying.")
    account = accounts[0]["account"]

    def gc(*arguments, capture=False):
        return run(gcloud + list(arguments) + [f"--project={args.project}", f"--account={account}", "--quiet"], capture=capture)

    project = json.loads(gc("projects", "describe", args.project, "--format=json", capture=True))
    if project.get("lifecycleState") != "ACTIVE":
        raise RuntimeError("The project is not active. Restore/create the project and link billing first.")
    runtime_sa = f"campusconnect-run@{args.project}.iam.gserviceaccount.com"
    principal = ("serviceAccount:" if account.endswith(".gserviceaccount.com") else "user:") + account
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    image = f"{args.region}-docker.pkg.dev/{args.project}/{NAME}/{NAME}:phase1-restore-{stamp}"
    print(f"Project: {args.project}\nAccount: {account}\nRegion: {args.region}\nBucket: {bucket}", flush=True)

    print("2/7 Enabling APIs and preparing the image repository", flush=True)
    gc("services", "enable", *APIS)
    repositories = json.loads(gc("artifacts", "repositories", "list", f"--location={args.region}", "--format=json", capture=True))
    repository = next((item for item in repositories if item["name"].endswith(f"/repositories/{NAME}")), None)
    if repository is None:
        gc("artifacts", "repositories", "create", NAME, "--repository-format=docker", f"--location={args.region}")
    elif repository.get("format") != "DOCKER" or repository.get("mode", "STANDARD_REPOSITORY") != "STANDARD_REPOSITORY":
        raise RuntimeError("Existing campusconnect repository must be a standard Docker repository.")

    print("3/7 Preparing runtime identity and permission to attach it", flush=True)
    identities = json.loads(gc("iam", "service-accounts", "list", "--format=json", capture=True))
    if not any(item["email"] == runtime_sa for item in identities):
        gc("iam", "service-accounts", "create", "campusconnect-run", "--display-name=CampusConnect runtime")
    gc("iam", "service-accounts", "add-iam-policy-binding", runtime_sa,
       f"--member={principal}", "--role=roles/iam.serviceAccountUser", "--condition=None")

    print("4/7 Preparing the private bucket, files and runtime read access", flush=True)
    buckets = gc("storage", "buckets", "list", "--format=value(name)", capture=True).splitlines()
    bucket_exists = bucket in {name.removeprefix("gs://").rstrip("/") for name in buckets}
    if not bucket_exists:
        gc("storage", "buckets", "create", f"gs://{bucket}", f"--location={args.region}",
           "--uniform-bucket-level-access", "--public-access-prevention", "--soft-delete-duration=0")
    else:
        gc("storage", "buckets", "update", f"gs://{bucket}",
           "--uniform-bucket-level-access", "--public-access-prevention")
    for filename in ("announcement.txt", "poster.svg"):
        gc("storage", "cp", str(ROOT / "sample-assets" / filename), f"gs://{bucket}/{filename}", "--no-clobber")
    gc("storage", "buckets", "add-iam-policy-binding", f"gs://{bucket}",
       f"--member=serviceAccount:{runtime_sa}", "--role=roles/storage.objectViewer")

    print("5/7 Building and pushing the optimised Linux AMD64 image", flush=True)
    gc("auth", "configure-docker", f"{args.region}-docker.pkg.dev")
    # Copy only runtime inputs: documents, nested clones and credentials never
    # enter the Docker build context, even if the working directory contains them.
    with tempfile.TemporaryDirectory(prefix="campusconnect-build-") as temporary:
        context = Path(temporary)
        for filename in ("app.py", "requirements.txt", "Dockerfile.optimised"):
            shutil.copy2(ROOT / filename, context / filename)
        for directory in ("templates", "sample-assets"):
            shutil.copytree(ROOT / directory, context / directory)
        run([docker, "build", "--platform", "linux/amd64", "-f", context / "Dockerfile.optimised", "-t", image, context])
    run([docker, "push", image])

    print("6/7 Deploying the storage application and routing traffic to it", flush=True)
    gc("run", "deploy", NAME, f"--image={image}", f"--region={args.region}", "--port=8080",
       f"--service-account={runtime_sa}", f"--update-env-vars=STORAGE_BUCKET={bucket}", "--allow-unauthenticated")
    gc("run", "services", "update-traffic", NAME, f"--region={args.region}", "--to-latest")
    url = gc("run", "services", "describe", NAME, f"--region={args.region}", "--format=value(status.url)", capture=True)
    if not url.startswith("https://"):
        raise RuntimeError("Cloud Run did not return an HTTPS service URL.")

    print(f"7/7 Verifying the public application and bucket-backed routes: {url}", flush=True)
    verify_service(url, args.verify_timeout)
    print("\nPhase 1 application is ready for Phase 2.")
    for key, value in (
        ("PROJECT_ID", args.project), ("REGION", args.region),
        ("REPOSITORY", NAME), ("SERVICE", NAME), ("BUCKET", bucket),
        ("RUNTIME_SA", runtime_sa), ("SERVICE_URL", url),
    ):
        print(f"{key}={value}")
    print("Continue with CI/CD guide section 3.2, then create the personal repository and WIF setup.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"\nRestore stopped: {error}", file=sys.stderr)
        print("Resources already created are retained. Correct the reported issue and rerun the same command.", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nStopped. Existing resources are retained; rerun to continue.", file=sys.stderr)
        sys.exit(130)
