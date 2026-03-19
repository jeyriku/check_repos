import json
import os
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
APPS=[(3,'checksysvers'),(6,'infrahub_jeylan'),(9,'nexuspush'),(4,'ipscanner'),(10,'jeypyats')]

for pid,repo in APPS:
    gl_req=urllib.request.Request(f'{BASE}/projects/{pid}/repository/tags', headers={'Authorization': f'Bearer {GL}'})
    with urllib.request.urlopen(gl_req, timeout=20) as r:
        gl_tags=[t['name'] for t in json.loads(r.read().decode())[:10]]
    gh_req=urllib.request.Request(f'https://api.github.com/repos/jeyriku/{repo}/tags?per_page=10', headers={'Authorization': f'Bearer {GH}', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(gh_req, timeout=20) as r:
        gh_tags=[t['name'] for t in json.loads(r.read().decode())[:10]]
    print(repo)
    print('  gitlab:', gl_tags)
    print('  github:', gh_tags)
