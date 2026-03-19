# check-repos

Package Python de vérification de synchronisation entre GitLab, GitHub et Nexus.

## Structure

```
check_repos/
├── check_repos/
│   ├── __init__.py
│   ├── credentials.py   ← chargement via jeyriku-vault
│   ├── sync.py          ← vérification versions, tags, mirrors
│   ├── mirrors.py       ← configuration remote mirrors GitLab -> GitHub
│   └── tags.py          ← création tags GitLab et GitHub
├── tests/
│   └── test_sync.py
├── pyproject.toml
└── README.md
```

## Installation

```bash
cd check_repos
python -m venv venv
source venv/bin/activate
pip install -e .
```

## Identifiants

Les scripts chargent les identifiants depuis **jeyriku-vault** :

| Service vault | Champ       | Utilisation                    |
|---------------|-------------|--------------------------------|
| `gitlab`      | `token`     | GITLAB_TOKEN                   |
| `github`      | `token`     | GITHUB_TOKEN + GITHUB_PUSH_TOKEN |
| `nexus`       | `username`  | NEXUS_USERNAME                 |
| `nexus`       | `password`  | NEXUS_PASSWORD                 |

Initialisation du vault (une seule fois) :

```bash
jeyriku-vault init
jeyriku-vault set gitlab --token VOTRE_TOKEN_GITLAB
jeyriku-vault set github --username jeyriku --token VOTRE_TOKEN_GITHUB
jeyriku-vault set nexus --username admin --password VOTRE_MDP_NEXUS
```

En environnement CI, définir la variable `VAULT_MASTER_PASSWORD` avec le mot de passe maître du vault.

## Utilisation

### Vérification de synchronisation

Par défaut, `check-repos` découvre automatiquement tous les projets GitLab
dont vous êtes membre (équivalent de `--include-all-gitlab-projects`).
Pour utiliser uniquement la liste fixe définie dans le code, passer `--no-auto-discover`.

```bash
check-repos
check-repos --check-tags --check-mirrors --json-out report.json --csv-out report.csv
check-repos --exclude-apps jeyapp,git-intro --check-tags --check-mirrors
check-repos --no-auto-discover   # liste fixe uniquement
```

### Configuration des mirrors GitHub

```bash
configure-mirrors                              # dry-run
configure-mirrors --apply
configure-mirrors --apply --create-missing-github --sync
```

### Création des tags de release

`create-tags` lit la version courante depuis le `pyproject.toml` de chaque
projet sur GitLab, puis crée le tag correspondant sur GitLab **et** GitHub
si ce tag n'existe pas encore.

```bash
create-tags
```

## Variables optionnelles (non-sensibles)

```bash
export GITLAB_BASE_URL="http://jeysrv12:8090"   # défaut
export GITHUB_OWNER="jeyriku"                   # défaut
export NEXUS_BASE_URL="http://jeysrv12:8081"    # défaut
export NEXUS_REPOSITORY="pypi-releases"         # défaut
```

## Tests

```bash
python -m pytest tests/ -v
```

## Code de retour de `check-repos`

- `0` : tout est synchronisé
- `1` : problème sur les versions
- `2` : problème sur les tags
- `4` : problème sur les mirrors GitHub

Les valeurs se cumulent (ex: `3` = versions + tags).

## Pipeline GitLab

Voir [.gitlab-ci.yml](.gitlab-ci.yml). Variable CI/CD à définir :

- `VAULT_MASTER_PASSWORD` (Protected + Masked)
