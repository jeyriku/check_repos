"""Inventorie et configure les remote mirrors GitLab -> GitHub."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from .credentials import load as load_credentials

GITLAB_BASE_URL = os.getenv("GITLAB_BASE_URL", "http://jeysrv12:8090").rstrip("/")
GITHUB_OWNER = os.getenv("GITHUB_OWNER", "jeyriku")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "jeyriku")
GITHUB_NEW_REPOS_PRIVATE = os.getenv("GITHUB_NEW_REPOS_PRIVATE", "false").lower() == "true"
TIMEOUT = 20


def fetch_json(url: str, headers: dict[str, str] | None = None, data: bytes | None = None, method: str | None = None):
    req = urllib.request.Request(url, headers=headers or {}, data=data, method=method)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def gitlab_headers(gitlab_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {gitlab_token}", "Content-Type": "application/json"}


def github_headers(github_token: str) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    return headers


def get_projects(gitlab_token: str) -> list[dict]:
    projects = []
    page = 1
    while True:
        url = f"{GITLAB_BASE_URL}/api/v4/projects?membership=true&simple=true&per_page=100&page={page}"
        data = fetch_json(url, headers=gitlab_headers(gitlab_token))
        if not data:
            break
        projects.extend(data)
        page += 1
    return projects


def github_repo_exists(repo_name: str, github_token: str) -> bool:
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{repo_name}"
    try:
        fetch_json(url, headers=github_headers(github_token))
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def create_github_repo(repo_name: str, github_token: str) -> dict:
    payload = {
        "name": repo_name,
        "private": GITHUB_NEW_REPOS_PRIVATE,
        "auto_init": False,
        "has_issues": True,
        "has_projects": True,
        "has_wiki": True,
    }
    return fetch_json(
        "https://api.github.com/user/repos",
        headers={**github_headers(github_token), "Content-Type": "application/json"},
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )


def get_remote_mirrors(project_id: int, gitlab_token: str) -> list[dict]:
    url = f"{GITLAB_BASE_URL}/api/v4/projects/{project_id}/remote_mirrors"
    data = fetch_json(url, headers=gitlab_headers(gitlab_token))
    return data if isinstance(data, list) else []


def create_remote_mirror(project_id: int, repo_name: str, gitlab_token: str, github_token: str) -> dict:
    mirror_url = f"https://{GITHUB_USERNAME}:{github_token}@github.com/{GITHUB_OWNER}/{repo_name}.git"
    payload = {
        "url": mirror_url,
        "enabled": True,
        "only_protected_branches": False,
        "keep_divergent_refs": True,
        "auth_method": "password",
    }
    url = f"{GITLAB_BASE_URL}/api/v4/projects/{project_id}/remote_mirrors"
    return fetch_json(url, headers=gitlab_headers(gitlab_token), data=json.dumps(payload).encode("utf-8"), method="POST")


def sync_remote_mirror(project_id: int, mirror_id: int, gitlab_token: str) -> bool:
    url = f"{GITLAB_BASE_URL}/api/v4/projects/{project_id}/remote_mirrors/{mirror_id}/sync"
    req = urllib.request.Request(url, headers=gitlab_headers(gitlab_token), data=b"", method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        return response.status == 204


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure les mirrors GitLab -> GitHub")
    parser.add_argument("--apply", action="store_true", help="Crée réellement les mirrors")
    parser.add_argument("--create-missing-github", action="store_true", help="Crée les repos GitHub manquants")
    parser.add_argument("--sync", action="store_true", help="Déclenche une synchronisation immédiate")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    creds = load_credentials()

    if not creds.gitlab_token:
        print("Erreur: credential 'gitlab' absent du vault.", file=sys.stderr)
        return 2
    if args.apply and not creds.github_token:
        print("Erreur: credential 'github' absent du vault pour --apply.", file=sys.stderr)
        return 2

    for project in sorted(get_projects(creds.gitlab_token), key=lambda item: item["id"]):
        path = project["path"]
        namespace = project["path_with_namespace"]
        project_id = project["id"]

        try:
            github_exists = github_repo_exists(path, creds.github_token)
        except Exception as exc:
            print(f"{namespace}: erreur GitHub -> {exc}")
            continue

        mirrors = get_remote_mirrors(project_id, creds.gitlab_token)
        github_mirror = next((m for m in mirrors if "github.com" in m.get("url", "")), None)

        if github_mirror:
            if args.apply and args.sync:
                sync_remote_mirror(project_id, github_mirror["id"], creds.gitlab_token)
                print(f"{namespace}: mirror GitHub déjà présent, synchro déclenchée")
            else:
                print(f"{namespace}: mirror GitHub déjà présent ({github_mirror.get('update_status', 'unknown')})")
            continue

        if not github_exists:
            if not args.create_missing_github:
                print(f"{namespace}: pas de repo GitHub correspondant")
                continue
            if not args.apply:
                print(f"{namespace}: repo GitHub manquant -> création possible (dry-run)")
                continue
            created_repo = create_github_repo(path, creds.github_token)
            print(f"{namespace}: repo GitHub créé ({created_repo.get('html_url')})")
            github_exists = True

        if not github_exists:
            print(f"{namespace}: pas de repo GitHub correspondant")
            continue

        if not args.apply:
            print(f"{namespace}: mirror GitHub possible -> https://github.com/{GITHUB_OWNER}/{path} (dry-run)")
            continue

        created = create_remote_mirror(project_id, path, creds.gitlab_token, creds.github_token)
        if args.sync:
            sync_remote_mirror(project_id, created["id"], creds.gitlab_token)
            print(f"{namespace}: mirror créé (id={created.get('id')}) + synchro déclenchée")
        else:
            print(f"{namespace}: mirror créé (id={created.get('id')})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
