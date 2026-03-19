#!/usr/bin/env python3
"""Inventorie et configure les remote mirrors GitLab -> GitHub.

Par défaut, le script fonctionne en dry-run.
Il essaie de faire correspondre chaque projet GitLab avec un dépôt GitHub du même nom.

Usage:
  source venv/bin/activate
  export GITLAB_TOKEN="..."
  export GITHUB_PUSH_TOKEN="..."
  python configure_gitlab_github_mirrors.py
  python configure_gitlab_github_mirrors.py --apply

Variables optionnelles:
  GITLAB_BASE_URL   défaut: http://jeysrv12:8090
  GITHUB_OWNER      défaut: jeyriku
  GITHUB_USERNAME   défaut: jeyriku
    GITHUB_NEW_REPOS_PRIVATE défaut: false
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

GITLAB_BASE_URL = os.getenv("GITLAB_BASE_URL", "http://jeysrv12:8090").rstrip("/")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN", "")
GITHUB_OWNER = os.getenv("GITHUB_OWNER", "jeyriku")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "jeyriku")
GITHUB_PUSH_TOKEN = os.getenv("GITHUB_PUSH_TOKEN", "")
GITHUB_NEW_REPOS_PRIVATE = os.getenv("GITHUB_NEW_REPOS_PRIVATE", "false").lower() == "true"
TIMEOUT = 20


def fetch_json(url: str, headers: dict[str, str] | None = None, data: bytes | None = None, method: str | None = None):
    req = urllib.request.Request(url, headers=headers or {}, data=data, method=method)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def gitlab_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {GITLAB_TOKEN}", "Content-Type": "application/json"}


def github_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_PUSH_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_PUSH_TOKEN}"
    return headers


def get_projects() -> list[dict]:
    projects = []
    page = 1
    while True:
        url = f"{GITLAB_BASE_URL}/api/v4/projects?membership=true&simple=true&per_page=100&page={page}"
        data = fetch_json(url, headers=gitlab_headers())
        if not data:
            break
        projects.extend(data)
        page += 1
    return projects


def github_repo_exists(repo_name: str) -> bool:
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{repo_name}"
    try:
        fetch_json(url, headers=github_headers())
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def create_github_repo(repo_name: str) -> dict:
    payload = {
        "name": repo_name,
        "private": GITHUB_NEW_REPOS_PRIVATE,
        "auto_init": False,
        "has_issues": True,
        "has_projects": True,
        "has_wiki": True,
    }
    url = "https://api.github.com/user/repos"
    return fetch_json(
        url,
        headers={**github_headers(), "Content-Type": "application/json"},
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )


def get_remote_mirrors(project_id: int) -> list[dict]:
    url = f"{GITLAB_BASE_URL}/api/v4/projects/{project_id}/remote_mirrors"
    data = fetch_json(url, headers=gitlab_headers())
    return data if isinstance(data, list) else []


def create_remote_mirror(project_id: int, repo_name: str) -> dict:
    mirror_url = f"https://{GITHUB_USERNAME}:{GITHUB_PUSH_TOKEN}@github.com/{GITHUB_OWNER}/{repo_name}.git"
    payload = {
        "url": mirror_url,
        "enabled": True,
        "only_protected_branches": False,
        "keep_divergent_refs": True,
        "auth_method": "password",
    }
    url = f"{GITLAB_BASE_URL}/api/v4/projects/{project_id}/remote_mirrors"
    return fetch_json(url, headers=gitlab_headers(), data=json.dumps(payload).encode("utf-8"), method="POST")


def sync_remote_mirror(project_id: int, mirror_id: int) -> bool:
    url = f"{GITLAB_BASE_URL}/api/v4/projects/{project_id}/remote_mirrors/{mirror_id}/sync"
    req = urllib.request.Request(url, headers=gitlab_headers(), data=b"", method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        return response.status == 204


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Configure les mirrors GitLab -> GitHub")
    parser.add_argument("--apply", action="store_true", help="Crée réellement les mirrors")
    parser.add_argument(
        "--create-missing-github",
        action="store_true",
        help="Crée les repos GitHub manquants avant de créer le mirror",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Déclenche une synchronisation immédiate des mirrors GitHub",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not GITLAB_TOKEN:
        print("Erreur: GITLAB_TOKEN absent", file=sys.stderr)
        return 2

    if args.apply and not GITHUB_PUSH_TOKEN:
        print("Erreur: GITHUB_PUSH_TOKEN absent pour --apply", file=sys.stderr)
        return 2

    for project in sorted(get_projects(), key=lambda item: item["id"]):
        path = project["path"]
        namespace = project["path_with_namespace"]
        project_id = project["id"]

        try:
            github_exists = github_repo_exists(path)
        except Exception as exc:
            print(f"{namespace}: erreur GitHub -> {exc}")
            continue

        mirrors = get_remote_mirrors(project_id)
        github_mirror = next((m for m in mirrors if "github.com" in m.get("url", "")), None)

        if github_mirror:
            if args.apply and args.sync:
                sync_remote_mirror(project_id, github_mirror["id"])
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
            created_repo = create_github_repo(path)
            print(f"{namespace}: repo GitHub créé ({created_repo.get('html_url')})")
            github_exists = True

        if not github_exists:
            print(f"{namespace}: pas de repo GitHub correspondant")
            continue

        if not args.apply:
            print(f"{namespace}: mirror GitHub possible -> https://github.com/{GITHUB_OWNER}/{path} (dry-run)")
            continue

        created = create_remote_mirror(project_id, path)
        if args.sync:
            sync_remote_mirror(project_id, created["id"])
            print(f"{namespace}: mirror créé (id={created.get('id')}) + synchro déclenchée")
        else:
            print(f"{namespace}: mirror créé (id={created.get('id')})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
