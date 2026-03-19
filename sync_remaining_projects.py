import json
import base64
import os
import re
import requests
from jeyriku_vault import VaultManager

_vault = VaultManager()
if not _vault.is_initialized():
    raise SystemExit("Vault non initialisé. Lancez 'jeyriku-vault init' d'abord.")
_vault.unlock(os.getenv("VAULT_MASTER_PASSWORD"))
try:
    GL = _vault.get_credential("gitlab").token or ""
    GH = _vault.get_credential("github").token or ""
finally:
    _vault.lock()
BASE='http://jeysrv12:8090/api/v4'
glh={'Authorization': f'Bearer {GL}'}
ghh={'Authorization': f'Bearer {GH}', 'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json'}


def ensure_github_tag(repo, branch, tag):
    gh_tag = requests.get(f'https://api.github.com/repos/jeyriku/{repo}/git/ref/tags/{tag}', headers=ghh, timeout=20)
    if gh_tag.status_code == 200:
        print(f'{repo}: GitHub tag {tag} already exists')
        return
    if gh_tag.status_code != 404:
        gh_tag.raise_for_status()

    head = requests.get(f'https://api.github.com/repos/jeyriku/{repo}/git/ref/heads/{branch}', headers=ghh, timeout=20)
    if head.status_code == 404 and branch == 'master':
        head = requests.get(f'https://api.github.com/repos/jeyriku/{repo}/git/ref/heads/main', headers=ghh, timeout=20)
    head.raise_for_status()
    sha = head.json()['object']['sha']

    payload = {'ref': f'refs/tags/{tag}', 'sha': sha}
    rr = requests.post(f'https://api.github.com/repos/jeyriku/{repo}/git/refs', headers=ghh, data=json.dumps(payload), timeout=20)
    if rr.status_code in (200, 201):
        print(f'{repo}: GitHub tag {tag} created')
        return
    if rr.status_code == 422:
        retry = requests.get(f'https://api.github.com/repos/jeyriku/{repo}/git/ref/tags/{tag}', headers=ghh, timeout=20)
        if retry.status_code == 200:
            print(f'{repo}: GitHub tag {tag} already exists')
            return
        print(f'{repo}: GitHub tag {tag} not created ({rr.status_code}) {rr.text[:200]}')
        return
    rr.raise_for_status()


def update_github_pyproject_version(repo, target_version):
    branch = 'main'
    content = requests.get(
        f'https://api.github.com/repos/jeyriku/{repo}/contents/pyproject.toml?ref={branch}',
        headers=ghh,
        timeout=30,
    )
    if content.status_code == 404:
        branch = 'master'
        content = requests.get(
            f'https://api.github.com/repos/jeyriku/{repo}/contents/pyproject.toml?ref={branch}',
            headers=ghh,
            timeout=30,
        )
    content.raise_for_status()
    payload = content.json()
    current = base64.b64decode(payload['content']).decode('utf-8')
    updated = re.sub(r'^version\s*=\s*"[^"]+"', f'version = "{target_version}"', current, flags=re.M)
    if updated == current:
        print(f'{repo}: GitHub pyproject already at {target_version}')
        return branch

    rr = requests.put(
        f'https://api.github.com/repos/jeyriku/{repo}/contents/pyproject.toml',
        headers=ghh,
        data=json.dumps(
            {
                'message': f'chore: align version with latest Nexus release {target_version}',
                'content': base64.b64encode(updated.encode()).decode(),
                'sha': payload['sha'],
                'branch': branch,
            }
        ),
        timeout=30,
    )
    rr.raise_for_status()
    print(f'{repo}: GitHub pyproject version updated to {target_version}')
    return branch

# 1. jeyapp: aligne la version GitLab/GitHub sur Nexus 0.1.48
pid = 7
project_path = 'jeyriku%2Fjeyapp'
target_version = '0.1.48'
raw = requests.get(f'{BASE}/projects/{project_path}/repository/files/pyproject.toml/raw?ref=master', headers=glh, timeout=30)
raw.raise_for_status()
updated = re.sub(r'^version\s*=\s*"[^"]+"', f'version = "{target_version}"', raw.text, flags=re.M)
commit_payload = {
    'branch': 'master',
    'commit_message': f'chore: align version with latest Nexus release {target_version}',
    'actions': [
        {
            'action': 'update',
            'file_path': 'pyproject.toml',
            'content': updated,
        }
    ]
}
r = requests.post(f'{BASE}/projects/{pid}/repository/commits', headers={**glh, 'Content-Type': 'application/json'}, json=commit_payload, timeout=30)
if r.status_code in (200, 201):
    print(f'jeyapp: pyproject version updated to {target_version} on GitLab')
else:
    print('jeyapp: commit skipped/failed', r.status_code, r.text[:200])

update_github_pyproject_version('jeyapp', target_version)

# Trigger mirror sync for jeyapp
mirrors = requests.get(f'{BASE}/projects/{pid}/remote_mirrors', headers=glh, timeout=20).json()
for mirror in mirrors:
    if 'github.com' in mirror.get('url', ''):
        requests.post(f'{BASE}/projects/{pid}/remote_mirrors/{mirror["id"]}/sync', headers=glh, timeout=20)
        print('jeyapp: mirror sync triggered')
        break

# 2. Create missing tags on GitLab and GitHub
items = [
    {'pid': 7, 'repo': 'jeyapp', 'tag': target_version, 'branch': 'master'},
    {'pid': 5, 'repo': 'mypublicip', 'tag': '0.1.0', 'branch': 'main'},
    {'pid': 8, 'repo': 'jeyriku-vault', 'tag': '1.0.0', 'branch': 'main'},
    {'pid': 11, 'repo': 'netalps_probe', 'tag': '0.1.8', 'branch': 'main'},
]

for item in items:
    tag = item['tag']
    pid = item['pid']
    repo = item['repo']
    branch = item['branch']
    gl_tag = requests.get(f"{BASE}/projects/{pid}/repository/tags/{tag}", headers=glh, timeout=20)
    if gl_tag.status_code == 404:
        rr = requests.post(f'{BASE}/projects/{pid}/repository/tags', headers=glh, data={'tag_name': tag, 'ref': branch, 'message': f'Release {tag}'}, timeout=20)
        rr.raise_for_status()
        print(f'{repo}: GitLab tag {tag} created')
    else:
        print(f'{repo}: GitLab tag {tag} already exists')

    ensure_github_tag(repo, branch, tag)
