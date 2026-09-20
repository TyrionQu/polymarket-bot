import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import github_cli as m


def test_load_github_token():
    with tempfile.TemporaryDirectory() as d:
        cfg = os.path.join(d, "config.yaml")
        with open(cfg, "w") as f:
            f.write("github:\n  token: ghp_faketoken123\n")
        assert m.load_github_token(cfg) == "ghp_faketoken123"


def test_write_gitignore_adds_missing_entries():
    with tempfile.TemporaryDirectory() as d:
        # Pre-seed with one required entry to confirm it isn't duplicated.
        with open(os.path.join(d, ".gitignore"), "w") as f:
            f.write("venv/\n")
        m.write_gitignore(d, "config.yaml")
        with open(os.path.join(d, ".gitignore")) as f:
            entries = [line.strip() for line in f if line.strip()]
        for required in {"config.yaml", "venv/", "__pycache__/", "*.pyc", ".env"}:
            assert required in entries, required
        assert entries.count("venv/") == 1


def test_authenticated_url():
    assert (
        m.authenticated_url("https://github.com/owner/repo.git")
        == "https://x-access-token@github.com/owner/repo.git"
    )


def test_git_askpass_env_cleans_up():
    with m.git_askpass_env("ghp_secret") as env:
        askpass = env["GIT_ASKPASS"]
        assert os.path.exists(askpass)
        assert env["GIT_PUSH_TOKEN"] == "ghp_secret"
        assert env["GIT_TERMINAL_PROMPT"] == "0"
    # The temp askpass helper must be removed once the context exits.
    assert not os.path.exists(askpass)


test_load_github_token()
test_write_gitignore_adds_missing_entries()
test_authenticated_url()
test_git_askpass_env_cleans_up()
print("DONE")
