"""Crée les tags de version GitLab et GitHub pour les apps suivies."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import sys

from .credentials import load as load_credentials

GITLAB_BASE_URL = os.getenv("GITLAB_BASE_URL", "http://jeysrv12:8090").rstrip("/")
GITHUB_OWNER = os.getenv("GITHUB_OWNER", "jeyriku")
TIMEOUT = 20

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


def gitlab_headers(gitlab_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {gitlab_token}", "Content-Type": "application/json"}


def github_headers(github_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json", "Content-Type": "application/json"}


def gitlab_branches(project_id: int, gitlab_token: str) -> list[str]:
    data = fetch_json(f"{GITLAB_BASE_URL}/api/v4/projects/{project_id}/repository/branches", headers=gitlab_headers(gitlab_token))
    return [item["name"] for item in data or []]


def github_branches(repo: str, github_token: str) -> list[str]:
    data = fetch_json(f"https://api.github.com/repos/{GITHUB_OWNER}/{repo}/branches", headers=github_headers(github_token))
    return [item["name"] for item in data or []]


def choose_branch(branches: list[str]) -> str:
    for candidate in ("main", "master"):
        if candidate in branches:
            return candidate
    return branches[0]


def gitlab_has_tag(project_id: int, tag: str, gitlab_token: str) -> bool:
    try:
        fetch_json(
            f"{GITLAB_BASE_URL}/api/v4/projects/{project_id}/repository/tags/{urllib.parse.quote(tag, safe='')}",
            headers=gitlab_headers(gitlab_token),
        )
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def github_has_tag(repo: str, tag: str, github_token: str) -> bool:
    try:
        fetch_json(
            f"https://api.github.com/repos/{GITHUB_OWNER}/{repo}/git/ref/tags/{urllib.parse.quote(tag, safe='')}",
            headers=github_headers(github_token),
        )
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def create_gitlab_tag(project_id: int, tag: str, ref: str, gitlab_token: str) -> None:
    payload = urllib.parse.urlencode({"tag_name": tag, "ref": ref, "message": f"Release {tag}"}).encode("utf-8")
    fetch_json(
        f"{GITLAB_BASE_URL}/api/v4/projects/{project_id}/repository/tags",
        headers={"Authorization": f"Bearer {gitlab_token}"},
        data=payload,
        method="POST",
    )


def github_ref_sha(repo: str, branch: str, github_token: str) -> str:
    data = fetch_json(
        f"https://api.github.com/repos/{GITHUB_OWNER}/{repo}/git/ref/heads/{branch}",
        headers=github_headers(github_token),
    )
    return data["object"]["sha"]


def create_github_tag(repo: str, tag: str, sha: str, github_token: str) -> None:
    payload = json.dumps({"ref": f"refs/tags/{tag}", "sha": sha}).encode("utf-8")
    fetch_json(
        f"https://api.github.com/repos/{GITHUB_OWNER}/{repo}/git/refs",
        headers=github_headers(github_token),
        data=payload,
        method="POST",
    )


def main() -> int:
    creds = load_credentials()

    if not creds.gitlab_token or not creds.github_token:
        print("Erreur: credentials 'gitlab' et/ou 'github' absents du vault.", file=sys.stderr)
        return 2

    for app in APPS:
        tag = app["version"]
        gl_branch = choose_branch(gitlab_branches(app["project_id"], creds.gitlab_token))
        gh_branch = choose_branch(github_branches(app["github_repo"], creds.github_token))

        if gitlab_has_tag(app["project_id"], tag, creds.gitlab_token):
            print(f"{app['github_repo']}: tag GitLab {tag} existe déjà")
        else:
            create_gitlab_tag(app["project_id"], tag, gl_branch, creds.gitlab_token)
            print(f"{app['github_repo']}: tag GitLab {tag} créé sur {gl_branch}")

        if github_has_tag(app["github_repo"], tag, creds.github_token):
            print(f"{app['github_repo']}: tag GitHub {tag} existe déjà")
        else:
            sha = github_ref_sha(app["github_repo"], gh_branch, creds.github_token)
            create_github_tag(app["github_repo"], tag, sha, creds.github_token)
            print(f"{app['github_repo']}: tag GitHub {tag} créé sur {gh_branch}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
