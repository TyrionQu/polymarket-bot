import argparse
import contextlib
import os
import stat
import subprocess
import sys
import tempfile

import requests
import yaml

GITHUB_API = "https://api.github.com"


def api_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


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
    resp = requests.get(f"{GITHUB_API}/user", headers=api_headers(token), timeout=10)
    if resp.status_code != 200:
        sys.exit(f"GitHub token check failed ({resp.status_code}): {resp.text}")
    return resp.json()


def ensure_repo(token: str, name: str, private: bool) -> dict:
    resp = requests.post(
        f"{GITHUB_API}/user/repos",
        headers=api_headers(token),
        json={"name": name, "private": private},
        timeout=10,
    )
    if resp.status_code == 201:
        print(f"[OK] Created repository: {resp.json()['full_name']}")
        return resp.json()
    if resp.status_code == 422:
        me = verify_token(token)
        get_resp = requests.get(f"{GITHUB_API}/repos/{me['login']}/{name}", headers=api_headers(token), timeout=10)
        if get_resp.status_code == 200:
            print(f"[OK] Repository already exists: {get_resp.json()['full_name']}")
            return get_resp.json()
    sys.exit(f"Failed to create repository ({resp.status_code}): {resp.text}")


def list_repos(token: str, limit: int) -> list:
    resp = requests.get(
        f"{GITHUB_API}/user/repos",
        headers=api_headers(token),
        params={"per_page": limit, "sort": "updated"},
        timeout=10,
    )
    if resp.status_code != 200:
        sys.exit(f"Failed to list repositories ({resp.status_code}): {resp.text}")
    return resp.json()


def delete_repo(token: str, full_name: str):
    resp = requests.delete(f"{GITHUB_API}/repos/{full_name}", headers=api_headers(token), timeout=10)
    if resp.status_code == 204:
        return
    if resp.status_code == 403:
        sys.exit("Delete failed (403): the token needs the 'delete_repo' scope.")
    sys.exit(f"Delete failed ({resp.status_code}): {resp.text}")


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


def authenticated_url(url: str) -> str:
    """Insert the x-access-token user so git prompts for a password the askpass helper answers."""
    return url.replace("https://", "https://x-access-token@", 1)


@contextlib.contextmanager
def git_askpass_env(token: str):
    # Keep the token out of argv/on-disk git config: hand it to git only via
    # an askpass helper that reads it from a short-lived env var.
    fd, askpass_path = tempfile.mkstemp(prefix="askpass_", suffix=".sh")
    try:
        with os.fdopen(fd, "w") as f:
            f.write('#!/bin/sh\nexec echo "$GIT_PUSH_TOKEN"\n')
        os.chmod(askpass_path, stat.S_IRWXU)
        yield {
            **os.environ,
            "GIT_ASKPASS": askpass_path,
            "GIT_PUSH_TOKEN": token,
            "GIT_TERMINAL_PROMPT": "0",
        }
    finally:
        os.remove(askpass_path)


def confirm(prompt: str) -> bool:
    return input(prompt).strip().lower() in {"y", "yes"}


def cmd_create(args, token, user):
    if args.dry_run:
        visibility = "public" if args.public else "private"
        print(f"[DRY RUN] Would create {visibility} repo '{args.name}' for {user['login']}.")
        return
    repo = ensure_repo(token, args.name, private=not args.public)
    print(f"[OK] Repository ready: {repo['html_url']}")


def cmd_push(args, token, user):
    repo_dir = os.getcwd()
    write_gitignore(repo_dir, os.path.basename(args.config))

    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        run_git(repo_dir, "init", "-b", args.branch)
    ensure_git_identity(repo_dir, user)

    run_git(repo_dir, "add", "-A")
    run_git(repo_dir, "reset", "--", os.path.basename(args.config))  # never stage the secrets file
    pending = run_git(repo_dir, "status", "--porcelain")

    if args.dry_run:
        print("[DRY RUN] Would commit the following changes and push:")
        print(pending or "  (working tree clean)")
        return

    if pending:
        run_git(repo_dir, "commit", "-m", args.message)
    else:
        print("[INFO] Nothing to commit.")

    repo = ensure_repo(token, args.name, private=not args.public)
    with git_askpass_env(token) as env:
        run_git(repo_dir, "push", "-u", authenticated_url(repo["clone_url"]), f"HEAD:{args.branch}", env=env)
    print(f"[OK] Pushed to {repo['html_url']}")


def cmd_clone(args, token, user):
    clone_url = f"https://github.com/{user['login']}/{args.name}.git"
    target = args.dir or args.name
    with git_askpass_env(token) as env:
        run_git(os.getcwd(), "clone", authenticated_url(clone_url), target, env=env)
    print(f"[OK] Cloned {user['login']}/{args.name} into {target}")


def cmd_list(args, token, user):
    repos = list_repos(token, args.limit)
    if not repos:
        print("No repositories found.")
        return
    for repo in repos:
        visibility = "private" if repo.get("private") else "public"
        print(f"  {repo['full_name']:45} [{visibility:7}] {repo['html_url']}")


def cmd_delete(args, token, user):
    full_name = f"{user['login']}/{args.name}"
    if args.dry_run:
        print(f"[DRY RUN] Would delete repository {full_name}.")
        return
    if not confirm(f"Permanently delete {full_name}? This cannot be undone. [y/n] "):
        print("Aborted.")
        return
    delete_repo(token, full_name)
    print(f"[OK] Deleted {full_name}")


def cmd_status(args, token, user):
    repo_dir = os.getcwd()
    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        print("Not a git repository (no .git here).")
        return
    print(run_git(repo_dir, "status", "-sb"))
    print("\nRemotes:")
    print(run_git(repo_dir, "remote", "-v") or "  (none)")


def cmd_pull(args, token, user):
    repo_dir = os.getcwd()
    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        sys.exit("Not a git repository (no .git here).")
    origin = run_git(repo_dir, "remote", "get-url", "origin")
    with git_askpass_env(token) as env:
        print(run_git(repo_dir, "pull", authenticated_url(origin), args.branch, env=env))


def main():
    parser = argparse.ArgumentParser(
        description="GitHub helper driven by config.yaml's token: create, push, clone, list, delete, status, pull."
    )
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Create a new GitHub repository")
    p_create.add_argument("--name", default=os.path.basename(os.getcwd()), help="Repository name")
    p_create.add_argument("--public", action="store_true", help="Create a public repo (default: private)")
    p_create.add_argument("--dry-run", action="store_true", help="Preview without creating")
    p_create.set_defaults(func=cmd_create)

    p_push = sub.add_parser("push", help="Commit local changes and push to GitHub")
    p_push.add_argument("--name", default=os.path.basename(os.getcwd()), help="Repository name")
    p_push.add_argument("--public", action="store_true", help="If the repo must be created, make it public")
    p_push.add_argument("--branch", default="main", help="Branch to push")
    p_push.add_argument("-m", "--message", default="Update project files", help="Commit message for staged changes")
    p_push.add_argument("--dry-run", action="store_true", help="Show what would be committed/pushed without doing it")
    p_push.set_defaults(func=cmd_push)

    p_clone = sub.add_parser("clone", help="Clone one of your repositories")
    p_clone.add_argument("--name", default=os.path.basename(os.getcwd()), help="Repository name")
    p_clone.add_argument("--dir", help="Target directory (default: repository name)")
    p_clone.set_defaults(func=cmd_clone)

    p_list = sub.add_parser("list", help="List your repositories")
    p_list.add_argument("--limit", type=int, default=30, help="Max repositories to show")
    p_list.set_defaults(func=cmd_list)

    p_delete = sub.add_parser("delete", help="Delete a repository (needs delete_repo scope)")
    p_delete.add_argument("--name", required=True, help="Repository name")
    p_delete.add_argument("--dry-run", action="store_true", help="Preview without deleting")
    p_delete.set_defaults(func=cmd_delete)

    p_status = sub.add_parser("status", help="Show local git status and remotes")
    p_status.set_defaults(func=cmd_status)

    p_pull = sub.add_parser("pull", help="Pull the latest changes from origin")
    p_pull.add_argument("--branch", default="main", help="Branch to pull")
    p_pull.set_defaults(func=cmd_pull)

    args = parser.parse_args()

    token = load_github_token(args.config)
    user = verify_token(token)
    print(f"[OK] Token is valid for GitHub user: {user['login']}")

    args.func(args, token, user)


if __name__ == "__main__":
    main()
