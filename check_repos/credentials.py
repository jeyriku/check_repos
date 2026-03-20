"""Chargement des identifiants depuis jeyriku-vault."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Credentials:
    gitlab_token: str
    github_token: str
    nexus_username: str
    nexus_password: str


def _load_from_env() -> Credentials:
    """Charge les identifiants depuis les variables d'environnement (mode CI)."""
    return Credentials(
        gitlab_token=os.getenv("GITLAB_TOKEN", ""),
        github_token=os.getenv("GITHUB_TOKEN", ""),
        nexus_username=os.getenv("NEXUS_USERNAME", ""),
        nexus_password=os.getenv("NEXUS_PASSWORD", ""),
    )


def load() -> Credentials:
    """Ouvre le vault, récupère tous les identifiants et le referme.

    Si le vault n'est pas disponible (mode CI), utilise les variables
    d'environnement GITLAB_TOKEN, GITHUB_TOKEN, NEXUS_USERNAME, NEXUS_PASSWORD.
    """
    from jeyriku_vault import VaultManager

    try:
        vault = VaultManager(backend="encrypted_file")
        if not vault.is_initialized():
            return _load_from_env()
        vault.unlock(os.getenv("VAULT_MASTER_PASSWORD"))
    except Exception:
        return _load_from_env()

    try:
        gitlab_token = ""
        github_token = ""
        nexus_username = ""
        nexus_password = ""
        try:
            gitlab_token = vault.get_credential("gitlab").token or ""
        except Exception:
            pass
        try:
            github_token = vault.get_credential("github").token or ""
        except Exception:
            pass
        try:
            nexus = vault.get_credential("nexus")
            nexus_username = nexus.username or ""
            nexus_password = nexus.password or ""
        except Exception:
            pass
        return Credentials(
            gitlab_token=gitlab_token,
            github_token=github_token,
            nexus_username=nexus_username,
            nexus_password=nexus_password,
        )
    finally:
        vault.lock()
