"""Upload the committed project to a Hugging Face Space (Docker SDK).

Usage (after `hf auth login` with a WRITE token):
    python deploy/deploy_hf.py <hf-username>/<space-name>
Uploads exactly the files tracked by git (same as GitHub), with deploy/huggingface/README.md as the Space card.
"""
import subprocess
import sys
from pathlib import Path

from huggingface_hub import HfApi, CommitOperationAdd

ROOT = Path(__file__).resolve().parents[1]


def main(repo_id):
    api = HfApi()
    api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    files = [f for f in files if f and f != "README.md" and not f.startswith("deploy/")]
    ops = [CommitOperationAdd(path_in_repo=f, path_or_fileobj=str(ROOT / f)) for f in files]
    ops.append(CommitOperationAdd(path_in_repo="README.md", path_or_fileobj=str(ROOT / "deploy/huggingface/README.md")))
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    api.create_commit(repo_id, repo_type="space", operations=ops, commit_message=f"Deploy {head} from GitHub main")
    print(f"uploaded {len(ops)} files -> https://huggingface.co/spaces/{repo_id}")


if __name__ == "__main__":
    main(sys.argv[1])
