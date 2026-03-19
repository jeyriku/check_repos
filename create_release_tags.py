#!/usr/bin/env python3
"""Crée les tags de version GitLab et GitHub pour les apps suivies dans check_repos."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

GITLAB_BASE_URL = os.getenv("GITLAB_BASE_URL", "http://jeysrv12:8090").rstrip("/")
GITHUB_OWNER = os.getenv("GITHUB_OWNER", "jeyriku")
TIMEOUT = 20


def _load_credentials() -> tuple[str, str]:
    """Charge les identifiants depuis jeyriku-vault."""
    from jeyriku_vault import VaultManager
    vault = VaultManager()
    if not vault.is_initialized():
        raise SystemExit("Vault non initialisé. Lancez 'jeyriku-vault init' d'abord.")
    vault.unlock(os.getenv("VAULT_MASTER_PASSWORD"))
    try:
        gitlab_token = ""
        github_token = ""
        try:
            gitlab_token = vault.get_credential("gitlab").token or ""
        except Exception:
            pass
        try:
            github_token = vault.get_credential("github").token or ""
        except Exception:
            pass
        return gitlab_token, github_token
    finally:
        vault.lock()


GITLAB_TOKEN, GITHUB_TOKEN = _load_credentials()

APPS = [
    {"project_id": 3, "gitlab_project": "jeyriku/checksysvers", "github_repo": "checksysvers", "version": "0.1.2"},
    {"project_id": 6, "gitlab_project": "jeyriku/infrahub_jeylan", "github_repo": "infrahub_jeylan", "version": "1.0.6"},
    {"project_id": 9, "gitlab_project": "jeyriku/nexuspush", "github_repo": "nexuspush", "version": "1.0.4"},
    {"project_id": 4, "gitlab_project": "jeyriku/ipscanner", "github_repo": "ipscanner", "version": "0.1.6"},
    {"project_id": 10, "gitlab_project": "jeyriku/jeypyats", "github_repo": "jeypyats", "version": "1.2.3"},
]


def fetch_json(url: str, headers: dict[str, str] | None = None, data: bytes | None = None, method: str | None = None):
    req = urllib.request.Request(url, headers=headers or {}, data=data, method=method)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else None


def gitlab_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {GITLAB_TOKEN}", "Content-Type": "application/json"}


def github_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json", "Content-Type": "application/json"}


def gitlab_branches(project_id: int) -> list[str]:
    data = fetch_json(f"{GITLAB_BASE_URL}/api/v4/projects/{project_id}/repository/branches", headers=gitlab_headers())
    return [item["name"] for item in data or []]


def github_branches(repo: str) -> list[str]:
    data = fetch_json(f"https://api.github.com/repos/{GITHUB_OWNER}/{repo}/branches", headers=github_headers())
    return [item["name"] for item in data or []]


def choose_branch(branches: list[str]) -> str:
    for candidate in ("main", "master"):
        if candidate in branches:
            return candidate
    return branches[0]


def gitlab_has_tag(project_id: int, tag: str) -> bool:
    try:
        fetch_json(f"{GITLAB_BASE_URL}/api/v4/projects/{project_id}/repository/tags/{urllib.parse.quote(tag, safe='')}", headers=gitlab_headers())
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def github_has_tag(repo: str, tag: str) -> bool:
    try:
        fetch_json(f"https://api.github.com/repos/{GITHUB_OWNER}/{repo}/git/ref/tags/{urllib.parse.quote(tag, safe='')}", headers=github_headers())
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def create_gitlab_tag(project_id: int, tag: str, ref: str) -> None:
    payload = urllib.parse.urlencode({"tag_name": tag, "ref": ref, "message": f"Release {tag}"}).encode("utf-8")
    fetch_json(f"{GITLAB_BASE_URL}/api/v4/projects/{project_id}/repository/tags", headers={"Authorization": f"Bearer {GITLAB_TOKEN}"}, data=payload, method="POST")


def github_ref_sha(repo: str, branch: str) -> str:
    data = fetch_json(f"https://api.github.com/repos/{GITHUB_OWNER}/{repo}/git/ref/heads/{branch}", headers=github_headers())
    return data["object"]["sha"]


def create_github_tag(repo: str, tag: str, sha: str) -> None:
    payload = json.dumps({"ref": f"refs/tags/{tag}", "sha": sha}).encode("utf-8")
    fetch_json(f"https://api.github.com/repos/{GITHUB_OWNER}/{repo}/git/refs", headers=github_headers(), data=payload, method="POST")


def main() -> int:
    if not GITLAB_TOKEN or not GITHUB_TOKEN:
        raise SystemExit("GITLAB_TOKEN and GITHUB_TOKEN are required")

    for app in APPS:
        tag = app["version"]
        gl_branch = choose_branch(gitlab_branches(app["project_id"]))
        gh_branch = choose_branch(github_branches(app["github_repo"]))

        if gitlab_has_tag(app["project_id"], tag):
            print(f"{app['github_repo']}: tag GitLab {tag} existe déjà")
        else:
            create_gitlab_tag(app["project_id"], tag, gl_branch)
            print(f"{app['github_repo']}: tag GitLab {tag} créé sur {gl_branch}")

        if github_has_tag(app["github_repo"], tag):
            print(f"{app['github_repo']}: tag GitHub {tag} existe déjà")
        else:
            sha = github_ref_sha(app["github_repo"], gh_branch)
            create_github_tag(app["github_repo"], tag, sha)
            print(f"{app['github_repo']}: tag GitHub {tag} créé sur {gh_branch}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
