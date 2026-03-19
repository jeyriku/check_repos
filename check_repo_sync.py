#!/usr/bin/env python3
"""Vérifie la synchronisation de version entre GitLab, GitHub et Nexus.

Le script compare, pour chaque application déclarée ci-dessous :
- la version présente dans le pyproject.toml sur GitLab
- la version présente dans le pyproject.toml sur GitHub
- la dernière version publiée sur Nexus

Options complémentaires :
- sortie JSON et CSV
- vérification des tags GitLab et GitHub
- vérification des remote mirrors GitLab vers GitHub

Code de retour :
- 0 : tout est synchronisé
- 1 : problème sur les versions
- 2 : problème sur les tags
- 4 : problème sur les mirrors GitHub

Usage:
  export GITLAB_TOKEN="..."
  export NEXUS_USERNAME="admin"
  export NEXUS_PASSWORD="..."
  source venv/bin/activate
  python check_repo_sync.py
  python check_repo_sync.py --check-tags --json-out report.json --csv-out report.csv

Variables optionnelles:
  GITLAB_BASE_URL   défaut: http://jeysrv12:8090
  GITHUB_OWNER      défaut: jeyriku
  NEXUS_BASE_URL    défaut: http://jeysrv12:8081
  NEXUS_REPOSITORY  défaut: pypi-releases
  GITHUB_TOKEN      optionnel, utile si rate limiting GitHub
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Iterable, Optional


GITLAB_BASE_URL = os.getenv("GITLAB_BASE_URL", "http://jeysrv12:8090").rstrip("/")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN", "")
GITHUB_OWNER = os.getenv("GITHUB_OWNER", "jeyriku")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
NEXUS_BASE_URL = os.getenv("NEXUS_BASE_URL", "http://jeysrv12:8081").rstrip("/")
NEXUS_REPOSITORY = os.getenv("NEXUS_REPOSITORY", "pypi-releases")
NEXUS_USERNAME = os.getenv("NEXUS_USERNAME", "")
NEXUS_PASSWORD = os.getenv("NEXUS_PASSWORD", "")
TIMEOUT = 15


@dataclass(frozen=True)
class AppConfig:
    label: str
    gitlab_project: str
    github_repo: str
    package_name: Optional[str]


APPS: list[AppConfig] = [
    AppConfig("checksysvers", "jeyriku/checksysvers", "checksysvers", "checksysvers"),
    AppConfig("infrahub_jeylan", "jeyriku/infrahub_jeylan", "infrahub_jeylan", "infrahub-jeylan"),
    AppConfig("nexuspush", "jeyriku/nexuspush", "nexuspush", "nexuspush"),
    AppConfig("ipscanner", "jeyriku/ipscanner", "ipscanner", "ipscanner"),
    AppConfig("jeypyats", "jeyriku/jeypyats", "jeypyats", "jeypyats"),
]


def fetch_text(url: str, headers: dict[str, str] | None = None) -> str:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read().decode("utf-8")


def fetch_json(url: str, headers: dict[str, str] | None = None) -> dict | list:
    return json.loads(fetch_text(url, headers=headers))


def parse_project_field_from_pyproject(pyproject_text: str, field_name: str) -> str:
    in_project_section = False
    for raw_line in pyproject_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line == "[project]":
            in_project_section = True
            continue
        if in_project_section and line.startswith("["):
            break
        if in_project_section and line.startswith(field_name):
            match = re.match(rf'{field_name}\s*=\s*["\']([^"\']+)["\']', line)
            if match:
                return match.group(1)
    raise ValueError(f"Champ project.{field_name} introuvable")


def parse_version_from_pyproject(pyproject_text: str) -> str:
    return parse_project_field_from_pyproject(pyproject_text, "version")


def parse_name_from_pyproject(pyproject_text: str) -> str:
    return parse_project_field_from_pyproject(pyproject_text, "name")


def version_key(version: str) -> tuple:
    parts = re.split(r"[._-]", version)
    normalized: list[int | str] = []
    for part in parts:
        if part.isdigit():
            normalized.append(int(part))
        else:
            normalized.append(part)
    return tuple(normalized)


def best_version(versions: Iterable[str]) -> str | None:
    clean = [version for version in versions if version]
    return max(clean, key=version_key) if clean else None


def normalize_tag(tag_name: str | None) -> str | None:
    if not tag_name:
        return None
    normalized = tag_name.strip()
    if normalized.lower().startswith("v") and len(normalized) > 1:
        normalized = normalized[1:]
    return normalized or None


def get_gitlab_projects() -> list[dict]:
    if not GITLAB_TOKEN:
        return []

    headers = {"Authorization": f"Bearer {GITLAB_TOKEN}"}
    projects: list[dict] = []
    page = 1
    while True:
        url = f"{GITLAB_BASE_URL}/api/v4/projects?membership=true&simple=true&per_page=100&page={page}"
        payload = fetch_json(url, headers=headers)
        if not isinstance(payload, list) or not payload:
            break
        projects.extend(payload)
        page += 1
    return projects


def get_gitlab_pyproject_text(project_path: str) -> str | None:
    if not GITLAB_TOKEN:
        return None

    encoded_project = urllib.parse.quote(project_path, safe="")
    headers = {"Authorization": f"Bearer {GITLAB_TOKEN}"}
    for branch in ("main", "master"):
        url = (
            f"{GITLAB_BASE_URL}/api/v4/projects/{encoded_project}"
            f"/repository/files/pyproject.toml/raw?ref={branch}"
        )
        try:
            return fetch_text(url, headers=headers)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            raise
    return None


def build_catalog(include_all_gitlab_projects: bool) -> list[AppConfig]:
    if not include_all_gitlab_projects:
        return APPS

    catalog: list[AppConfig] = []
    for project in sorted(get_gitlab_projects(), key=lambda item: item["id"]):
        project_path = project["path_with_namespace"]
        repo_name = project["path"]
        pyproject_text = get_gitlab_pyproject_text(project_path)
        package_name: Optional[str] = None
        if pyproject_text:
            try:
                package_name = parse_name_from_pyproject(pyproject_text)
            except ValueError:
                package_name = None
        catalog.append(
            AppConfig(
                label=repo_name,
                gitlab_project=project_path,
                github_repo=repo_name,
                package_name=package_name,
            )
        )
    return catalog


def parse_excluded_apps(raw_value: str | None) -> set[str]:
    if not raw_value:
        return set()
    return {item.strip() for item in raw_value.split(",") if item.strip()}


def get_gitlab_version(app: AppConfig) -> str | None:
    pyproject_text = get_gitlab_pyproject_text(app.gitlab_project)
    if pyproject_text is None:
        return None
    try:
        return parse_version_from_pyproject(pyproject_text)
    except ValueError:
        return None
    return None


def get_github_version(app: AppConfig) -> str | None:
    headers: dict[str, str] = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    headers["Accept"] = "application/vnd.github+json"

    for branch in ("main", "master"):
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{app.github_repo}/contents/pyproject.toml?ref={branch}"
        try:
            payload = fetch_json(url, headers=headers)
            if not isinstance(payload, dict) or "content" not in payload:
                continue
            content = base64.b64decode(payload["content"]).decode("utf-8")
            return parse_version_from_pyproject(content)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            raise
    return None


def get_gitlab_latest_tag(app: AppConfig) -> str | None:
    if not GITLAB_TOKEN:
        return None

    encoded_project = urllib.parse.quote(app.gitlab_project, safe="")
    headers = {"Authorization": f"Bearer {GITLAB_TOKEN}"}
    url = f"{GITLAB_BASE_URL}/api/v4/projects/{encoded_project}/repository/tags?per_page=100"
    payload = fetch_json(url, headers=headers)
    if not isinstance(payload, list):
        return None
    tags = [normalize_tag(item.get("name")) for item in payload]
    return best_version(tag for tag in tags if tag)


def get_github_latest_tag(app: AppConfig) -> str | None:
    headers: dict[str, str] = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{app.github_repo}/tags?per_page=100"
    try:
        payload = fetch_json(url, headers=headers)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise

    if not isinstance(payload, list):
        return None
    tags = [normalize_tag(item.get("name")) for item in payload]
    return best_version(tag for tag in tags if tag)


def get_gitlab_remote_mirrors(app: AppConfig) -> list[dict]:
    if not GITLAB_TOKEN:
        return []

    encoded_project = urllib.parse.quote(app.gitlab_project, safe="")
    headers = {"Authorization": f"Bearer {GITLAB_TOKEN}"}
    url = f"{GITLAB_BASE_URL}/api/v4/projects/{encoded_project}/remote_mirrors"
    payload = fetch_json(url, headers=headers)
    return payload if isinstance(payload, list) else []


def extract_github_mirror_status(app: AppConfig) -> tuple[str, str, str]:
    mirrors = get_gitlab_remote_mirrors(app)
    for mirror in mirrors:
        url = mirror.get("url", "")
        if "github.com" not in url:
            continue
        enabled = "YES" if mirror.get("enabled") else "NO"
        update_status = mirror.get("update_status") or "unknown"
        last_error = (mirror.get("last_error") or "").lower()
        benign_tag_conflict = "already exists" in last_error or "cannot lock ref 'refs/tags/" in last_error
        sync = "OK" if mirror.get("enabled") and (update_status == "finished" or benign_tag_conflict) else "ISSUE"
        return enabled, update_status, sync
    return "NO", "missing", "MISSING"


def get_nexus_version(app: AppConfig) -> str | None:
    if not app.package_name:
        return None

    auth = base64.b64encode(f"{NEXUS_USERNAME}:{NEXUS_PASSWORD}".encode("utf-8")).decode("ascii")
    headers = {"Authorization": f"Basic {auth}"}
    url = (
        f"{NEXUS_BASE_URL}/service/rest/v1/search?repository={NEXUS_REPOSITORY}"
        f"&name={urllib.parse.quote(app.package_name, safe='')}"
    )
    payload = fetch_json(url, headers=headers)
    items = payload.get("items", []) if isinstance(payload, dict) else []
    versions = [item.get("version") for item in items if item.get("version")]
    return best_version(versions)


def source_status(found: str | None, expected: str | None) -> str:
    if expected is None:
        return "UNKNOWN"
    if found is None:
        return "MISSING"
    if found == expected:
        return "OK"
    return "OUTDATED"


def build_headers(include_tags: bool) -> list[str]:
    headers = [
        "app",
        "expected",
        "gitlab",
        "gitlab_status",
        "github",
        "github_status",
        "nexus",
        "nexus_status",
        "versions_sync",
    ]
    if include_tags:
        headers.extend([
            "gitlab_tag",
            "gitlab_tag_status",
            "github_tag",
            "github_tag_status",
            "tags_sync",
        ])
    return headers


def extend_headers_for_mirrors(headers: list[str], include_mirrors: bool) -> list[str]:
    if include_mirrors:
        headers.extend([
            "github_mirror_enabled",
            "github_mirror_update_status",
            "github_mirror_status",
        ])
    return headers


def compute_exit_code(versions_failed: bool, tags_failed: bool, mirrors_failed: bool) -> int:
    code = 0
    if versions_failed:
        code |= 1
    if tags_failed:
        code |= 2
    if mirrors_failed:
        code |= 4
    return code


def print_table(rows: list[dict[str, str]], headers: list[str]) -> None:
    widths = {header: len(header) for header in headers}
    for row in rows:
        for header in headers:
            widths[header] = max(widths[header], len(str(row[header])))

    def fmt(row: dict[str, str]) -> str:
        return " | ".join(str(row[h]).ljust(widths[h]) for h in headers)

    print(fmt({header: header for header in headers}))
    print("-+-".join("-" * widths[header] for header in headers))
    for row in rows:
        print(fmt(row))


def write_json(rows: list[dict[str, str]], output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(rows, handle, indent=2, ensure_ascii=False)


def write_csv(rows: list[dict[str, str]], headers: list[str], output_path: str) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vérifie la synchro GitLab / GitHub / Nexus")
    parser.add_argument(
        "--check-tags",
        action="store_true",
        help="Vérifie aussi les tags GitLab et GitHub",
    )
    parser.add_argument(
        "--json-out",
        help="Chemin de sortie JSON pour le rapport",
    )
    parser.add_argument(
        "--csv-out",
        help="Chemin de sortie CSV pour le rapport",
    )
    parser.add_argument(
        "--check-mirrors",
        action="store_true",
        help="Vérifie aussi la présence et l'état des remote mirrors GitHub côté GitLab",
    )
    parser.add_argument(
        "--include-all-gitlab-projects",
        action="store_true",
        help="Inclut tous les projets GitLab accessibles, pas seulement les 5 apps packagées",
    )
    parser.add_argument(
        "--exclude-apps",
        default=os.getenv("CHECK_REPOS_EXCLUDE_APPS", ""),
        help="Liste d'applications a exclure, separees par des virgules",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    excluded_apps = parse_excluded_apps(args.exclude_apps)

    if not GITLAB_TOKEN:
        print("Erreur: variable GITLAB_TOKEN absente.", file=sys.stderr)
        return 2
    if not NEXUS_USERNAME or not NEXUS_PASSWORD:
        print("Erreur: variables NEXUS_USERNAME/NEXUS_PASSWORD absentes.", file=sys.stderr)
        return 2

    rows: list[dict[str, str]] = []
    versions_failed = False
    tags_failed = False
    mirrors_failed = False

    for app in build_catalog(args.include_all_gitlab_projects):
        if app.label in excluded_apps:
            continue
        gitlab_version = get_gitlab_version(app)
        github_version = get_github_version(app)
        nexus_version = get_nexus_version(app)
        expected = best_version([gitlab_version, github_version, nexus_version])

        if expected is None:
            gitlab_status = "SKIPPED"
            github_status = "SKIPPED"
            nexus_status = "SKIPPED"
            versions_sync = "SKIPPED"
        else:
            gitlab_status = source_status(gitlab_version, expected)
            github_status = source_status(github_version, expected)
            nexus_status = source_status(nexus_version, expected)
            versions_sync = "YES" if all(status == "OK" for status in (gitlab_status, github_status, nexus_status)) else "NO"

        if versions_sync != "YES":
            if versions_sync != "SKIPPED":
                versions_failed = True

        row = {
            "app": app.label,
            "expected": expected or "n/a",
            "gitlab": gitlab_version or "n/a",
            "gitlab_status": gitlab_status,
            "github": github_version or "n/a",
            "github_status": github_status,
            "nexus": nexus_version or "n/a",
            "nexus_status": nexus_status,
            "versions_sync": versions_sync,
        }

        if args.check_tags:
            gitlab_tag = get_gitlab_latest_tag(app)
            github_tag = get_github_latest_tag(app)
            expected_tag = best_version([value for value in [expected, gitlab_tag, github_tag] if value])
            if expected_tag is None:
                gitlab_tag_status = "SKIPPED"
                github_tag_status = "SKIPPED"
                tags_sync = "SKIPPED"
            else:
                gitlab_tag_status = source_status(gitlab_tag, expected_tag)
                github_tag_status = source_status(github_tag, expected_tag)
                tags_sync = "YES" if all(status == "OK" for status in (gitlab_tag_status, github_tag_status)) else "NO"

            if tags_sync != "YES":
                if tags_sync != "SKIPPED":
                    tags_failed = True

            row.update(
                {
                    "gitlab_tag": gitlab_tag or "n/a",
                    "gitlab_tag_status": gitlab_tag_status,
                    "github_tag": github_tag or "n/a",
                    "github_tag_status": github_tag_status,
                    "tags_sync": tags_sync,
                }
            )

        if args.check_mirrors:
            mirror_enabled, mirror_update_status, mirror_status = extract_github_mirror_status(app)
            if mirror_status != "OK":
                mirrors_failed = True
            row.update(
                {
                    "github_mirror_enabled": mirror_enabled,
                    "github_mirror_update_status": mirror_update_status,
                    "github_mirror_status": mirror_status,
                }
            )

        row["overall_sync"] = "YES"
        if row["versions_sync"] not in ("YES", "SKIPPED"):
            row["overall_sync"] = "NO"
        if args.check_tags and row.get("tags_sync") not in ("YES", "SKIPPED"):
            row["overall_sync"] = "NO"
        if args.check_mirrors and row.get("github_mirror_status") != "OK":
            row["overall_sync"] = "NO"

        rows.append(row)

    headers = build_headers(args.check_tags)
    headers = extend_headers_for_mirrors(headers, args.check_mirrors)
    headers.append("overall_sync")
    print_table(rows, headers)

    if args.json_out:
        write_json(rows, args.json_out)
    if args.csv_out:
        write_csv(rows, headers, args.csv_out)

    return compute_exit_code(versions_failed, tags_failed, mirrors_failed)


if __name__ == "__main__":
    raise SystemExit(main())
