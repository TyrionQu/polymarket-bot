import argparse
import os
import stat
import subprocess
import sys
import tempfile

import requests
import yaml

GITHUB_API = "https://api.github.com"


def load_github_token(config_path: str) -> str:
    if not os.path.exists(config_path):
        sys.exit(f"Config file not found: {config_path}")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f) or {}
    token = (config.get("github") or {}).get("token", "").strip()
    if not token:
        sys.exit(f"No github.token found in {config_path}")
    return token


def verify_token(token: str) -> dict:
    resp = requests.get(
        f"{GITHUB_API}/user",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=10,
    )
    if resp.status_code != 200:
        sys.exit(f"GitHub token check failed ({resp.status_code}): {resp.text}")
    return resp.json()


def ensure_repo(token: str, name: str, private: bool) -> dict:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    resp = requests.post(
        f"{GITHUB_API}/user/repos",
        headers=headers,
        json={"name": name, "private": private},
        timeout=10,
    )
    if resp.status_code == 201:
        print(f"[OK] Created repository: {resp.json()['full_name']}")
        return resp.json()
    if resp.status_code == 422:
        me = verify_token(token)
        get_resp = requests.get(f"{GITHUB_API}/repos/{me['login']}/{name}", headers=headers, timeout=10)
        if get_resp.status_code == 200:
            print(f"[OK] Repository already exists: {get_resp.json()['full_name']}")
            return get_resp.json()
    sys.exit(f"Failed to create repository ({resp.status_code}): {resp.text}")


def run_git(repo_dir, *args, env=None):
    result = subprocess.run(
        ["git", "-C", repo_dir, *args], capture_output=True, text=True, env=env
    )
    if result.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed:\n{result.stderr}")
    return result.stdout.strip()


def ensure_git_identity(repo_dir: str, user: dict):
    def get(key):
        r = subprocess.run(["git", "-C", repo_dir, "config", "--get", key], capture_output=True, text=True)
        return r.stdout.strip()

    if not get("user.name"):
        run_git(repo_dir, "config", "user.name", user.get("name") or user["login"])
    if not get("user.email"):
        run_git(repo_dir, "config", "user.email", f"{user['id']}+{user['login']}@users.noreply.github.com")


def write_gitignore(repo_dir: str, config_filename: str):
    path = os.path.join(repo_dir, ".gitignore")
    required = {config_filename, "venv/", "__pycache__/", "*.pyc", ".env"}
    existing = set()
    if os.path.exists(path):
        with open(path) as f:
            existing = {line.strip() for line in f if line.strip()}
    missing = sorted(required - existing)
    if missing:
        with open(path, "a") as f:
            for entry in missing:
                f.write(entry + "\n")


def push_with_token(repo_dir: str, clone_url: str, token: str, branch: str):
    # Keep the token out of argv/on-disk git config: hand it to git only via
    # an askpass helper that reads it from a short-lived env var.
    fd, askpass_path = tempfile.mkstemp(prefix="askpass_", suffix=".sh")
    try:
        with os.fdopen(fd, "w") as f:
            f.write('#!/bin/sh\nexec echo "$GIT_PUSH_TOKEN"\n')
        os.chmod(askpass_path, stat.S_IRWXU)

        push_url = clone_url.replace("https://", "https://x-access-token@", 1)
        env = {
            **os.environ,
            "GIT_ASKPASS": askpass_path,
            "GIT_PUSH_TOKEN": token,
            "GIT_TERMINAL_PROMPT": "0",
        }
        run_git(repo_dir, "push", "-u", push_url, f"HEAD:{branch}", env=env)
    finally:
        os.remove(askpass_path)


def main():
    parser = argparse.ArgumentParser(description="Verify config.yaml's GitHub token and publish this project.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--name", default=os.path.basename(os.getcwd()), help="Repository name")
    parser.add_argument("--public", action="store_true", help="Create a public repo (default: private)")
    parser.add_argument("--branch", default="main", help="Branch to push")
    args = parser.parse_args()

    repo_dir = os.getcwd()

    token = load_github_token(args.config)
    user = verify_token(token)
    print(f"[OK] Token is valid for GitHub user: {user['login']}")

    write_gitignore(repo_dir, os.path.basename(args.config))

    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        run_git(repo_dir, "init", "-b", args.branch)
    ensure_git_identity(repo_dir, user)

    run_git(repo_dir, "add", "-A")
    run_git(repo_dir, "reset", "--", os.path.basename(args.config))  # never stage the secrets file
    if run_git(repo_dir, "status", "--porcelain"):
        run_git(repo_dir, "commit", "-m", "Initial commit")
    else:
        print("[INFO] Nothing to commit.")

    repo = ensure_repo(token, args.name, private=not args.public)
    push_with_token(repo_dir, repo["clone_url"], token, args.branch)
    print(f"[OK] Pushed to {repo['html_url']}")


if __name__ == "__main__":
    main()
