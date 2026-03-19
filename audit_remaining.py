import os
import requests

GL=os.environ['GITLAB_TOKEN']
GH=os.environ['GITHUB_TOKEN']
NEXUS_USERNAME=os.environ['NEXUS_USERNAME']
NEXUS_PASSWORD=os.environ['NEXUS_PASSWORD']
BASE='http://jeysrv12:8090/api/v4'
glh={'Authorization': f'Bearer {GL}'}
ghh={'Authorization': f'Bearer {GH}', 'Accept': 'application/vnd.github+json'}
checks=[('jeyapp',7,'jeyapp','jeyapp'),('mypublicip',5,'mypublicip','mypublicip'),('jeyriku-vault',8,'jeyriku-vault','jeyriku-vault'),('netalps_probe',11,'netalps_probe','netalps-probe')]
for label,pid,repo,pkg in checks:
    print('---', label)
    tags_gl=requests.get(f'{BASE}/projects/{pid}/repository/tags',headers=glh,timeout=20).json()
    print('gitlab tags:', [t['name'] for t in tags_gl[:10]])
    tags_gh=requests.get(f'https://api.github.com/repos/jeyriku/{repo}/tags?per_page=10',headers=ghh,timeout=20).json()
    print('github tags:', [t['name'] for t in tags_gh[:10]])
    r=requests.get(f'http://jeysrv12:8081/service/rest/v1/search?repository=pypi-releases&name={pkg}',auth=(NEXUS_USERNAME,NEXUS_PASSWORD),timeout=20)
    items=r.json().get('items',[]) if r.ok else []
    print('nexus versions:', [i['version'] for i in items])
    for branch in ['main','master']:
        url=f'{BASE}/projects/{pid}/repository/files/pyproject.toml/raw?ref={branch}'
        rr=requests.get(url,headers=glh,timeout=20)
        if rr.ok:
            print('branch:', branch)
            for line in rr.text.splitlines():
                if line.startswith('name =') or line.startswith('version ='):
                    print(line)
            break
