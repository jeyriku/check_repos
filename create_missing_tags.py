import json
import os
import urllib.error
import urllib.parse
import urllib.request
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
APPS=[(4,'ipscanner','0.1.6'),(10,'jeypyats','1.2.3')]


def fetch_json(url, headers=None, data=None, method=None):
    req=urllib.request.Request(url, headers=headers or {}, data=data, method=method)
    with urllib.request.urlopen(req, timeout=20) as r:
        body=r.read().decode()
        return json.loads(body) if body else None

for pid,repo,tag in APPS:
    glh={'Authorization': f'Bearer {GL}'}
    ghh={'Authorization': f'Bearer {GH}', 'Accept':'application/vnd.github+json', 'Content-Type':'application/json'}
    try:
        fetch_json(f'{BASE}/projects/{pid}/repository/tags/{urllib.parse.quote(tag, safe="")}', headers=glh)
        print(repo, 'gitlab tag exists')
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            branches=fetch_json(f'{BASE}/projects/{pid}/repository/branches', headers=glh)
            ref='main' if any(b['name']=='main' for b in branches) else 'master'
            payload=urllib.parse.urlencode({'tag_name': tag, 'ref': ref, 'message': f'Release {tag}'}).encode()
            fetch_json(f'{BASE}/projects/{pid}/repository/tags', headers={'Authorization': f'Bearer {GL}'}, data=payload, method='POST')
            print(repo, 'gitlab tag created', tag)
        else:
            raise
    try:
        fetch_json(f'https://api.github.com/repos/jeyriku/{repo}/git/ref/tags/{urllib.parse.quote(tag, safe="")}', headers=ghh)
        print(repo, 'github tag exists')
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            refs=fetch_json(f'https://api.github.com/repos/jeyriku/{repo}/git/ref/heads/main', headers=ghh)
            sha=refs['object']['sha']
            payload=json.dumps({'ref': f'refs/tags/{tag}', 'sha': sha}).encode()
            fetch_json(f'https://api.github.com/repos/jeyriku/{repo}/git/refs', headers=ghh, data=payload, method='POST')
            print(repo, 'github tag created', tag)
        else:
            raise
