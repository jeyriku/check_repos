# check_repos

Scripts de verification de synchronisation entre GitLab, GitHub et Nexus.

Le dossier contient a la fois :

- un controle cible sur les applications packagées
- un mode d'inventaire complet de tous les projets GitLab accessibles
- une pipeline GitLab prete a l'emploi pour automatiser les verifications

## Contenu

- `check_repo_sync.py` : verifie les versions, les tags et les remote mirrors GitLab -> GitHub.
- `configure_gitlab_github_mirrors.py` : inventorie, cree et synchronise les remote mirrors GitLab -> GitHub.
- `create_release_tags.py` : cree les tags GitLab et GitHub correspondant aux versions de release des applications suivies.
- `.gitlab-ci.yml` : pipeline GitLab pour automatiser le controle.
- `report.json` : dernier rapport JSON genere.
- `report.csv` : dernier rapport CSV genere.

## Environnement

Un environnement virtuel dedie est present dans `venv/`.

Activation :

```bash
cd /Users/jeremierouzet/Documents/Dev/check_repos
source venv/bin/activate
```

## Variables d'environnement

### Pour la verification de synchro

```bash
export GITLAB_TOKEN="..."
export NEXUS_USERNAME="admin"
export NEXUS_PASSWORD="..."
export GITHUB_TOKEN="..."
```

### Pour la configuration des mirrors GitHub

```bash
export GITLAB_TOKEN="..."
export GITHUB_PUSH_TOKEN="..."
```

## Verification complete

```bash
python check_repo_sync.py --check-tags --check-mirrors --json-out report.json --csv-out report.csv
```

## Verification de tous les projets GitLab

Ce mode inclut tous les projets GitLab accessibles avec le token fourni.

- pour les projets packagés Python : verification versions, tags et mirrors
- pour les projets sans `pyproject.toml` : verification du mirror GitHub, et statut `SKIPPED` pour versions/tags

```bash
python check_repo_sync.py --include-all-gitlab-projects --check-tags --check-mirrors --json-out report.json --csv-out report.csv
```

Exclusion ciblee possible pour des projets volontairement volatils :

```bash
python check_repo_sync.py --include-all-gitlab-projects --exclude-apps jeyapp --check-tags --check-mirrors
```

## Code de retour de `check_repo_sync.py`

- `0` : tout est synchronise
- `1` : probleme sur les versions
- `2` : probleme sur les tags
- `4` : probleme sur les mirrors GitHub

Les valeurs se cumulent :

- `3` = versions + tags
- `5` = versions + mirrors
- `6` = tags + mirrors
- `7` = versions + tags + mirrors

## Configuration des mirrors GitHub

### Inventaire sans modification

```bash
python configure_gitlab_github_mirrors.py
```

### Creation effective des mirrors

```bash
python configure_gitlab_github_mirrors.py --apply
```

### Creation des repos GitHub manquants + synchro immediate

```bash
python configure_gitlab_github_mirrors.py --apply --create-missing-github --sync
```

## Creation des tags de release

```bash
python create_release_tags.py
```

## Pipeline GitLab

Le fichier [check_repos/.gitlab-ci.yml](check_repos/.gitlab-ci.yml) est pret pour une execution automatique dans GitLab.

Commande executee par la pipeline :

```bash
python check_repo_sync.py --include-all-gitlab-projects --exclude-apps jeyapp --check-tags --check-mirrors --json-out report.json --csv-out report.csv
```

`jeyapp` est exclu dans la pipeline car sa version Nexus evolue pendant l'execution des jobs et genere des faux negatifs transitoires.

Variables CI/CD a definir dans le projet GitLab qui portera ce dossier :

- `GITLAB_TOKEN`
- `NEXUS_USERNAME`
- `NEXUS_PASSWORD`
- `GITHUB_TOKEN`

Les rapports `report.json` et `report.csv` sont publies en artifacts.

Le dossier `check_repos` n'est pas encore un depot Git autonome. Pour activer cette pipeline, il faut soit :

- versionner ce dossier dans un depot GitLab dedie
- ou l'integrer dans un depot GitLab existant

## Etat attendu actuel

Pour les 5 applications suivies :

- versions GitLab : OK
- versions GitHub : OK
- versions Nexus : OK
- tags GitLab : OK
- tags GitHub : OK
- mirrors GitLab -> GitHub : OK

Pour les autres projets GitLab :

- mirror GitHub : attendu OK
- versions/tags : `SKIPPED` si le projet n'est pas un package Python avec `pyproject.toml`
