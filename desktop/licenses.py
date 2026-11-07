"""Copy installed runtime dependency notices into the local installer payload."""
from pathlib import Path
import importlib.metadata as metadata,json,shutil
root=Path(__file__).resolve().parents[1];target=root/'release/FormaStudio/ThirdParty-Licenses';target.mkdir(parents=True,exist_ok=True)
inventory=[]
for line in (root/'backend/requirements-lock.txt').read_text().splitlines():
    if '==' not in line:continue
    name=line.split('==')[0]
    distribution=metadata.distribution(name)
    inventory.append({'name':name,'version':distribution.version,'license':distribution.metadata.get('License-Expression') or distribution.metadata.get('License'),'homepage':distribution.metadata.get('Home-page')})
    for file in distribution.files or []:
        if ('.dist-info/' in str(file).replace('\\','/')) and any(term in str(file).lower() for term in ('license','copying','notice')):
            source=distribution.locate_file(file)
            if source.is_file():
                destination=target/name/str(file).split('.dist-info',1)[1].lstrip('/\\');destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
(target/'inventory.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
for name in ('MODEL-LICENSES.md','CLOUD-PROVIDERS.md'):
    shutil.copy2(root/'docs'/name,target/name)
