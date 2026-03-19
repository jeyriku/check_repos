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


def load() -> Credentials:
    """Ouvre le vault, récupère tous les identifiants et le referme."""
    from jeyriku_vault import VaultManager

    vault = VaultManager()
    if not vault.is_initialized():
        raise SystemExit("Vault non initialisé. Lancez 'jeyriku-vault init' d'abord.")
    vault.unlock(os.getenv("VAULT_MASTER_PASSWORD"))
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
