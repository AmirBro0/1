import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
files=[]
for path in sorted((root/'web/assets').rglob('*')):
    if not path.is_file():continue
    relative=path.relative_to(root).as_posix()
    if '/worlds/' in relative:
        source='Built-in image_gen for this project';version='2026-10-18';terms='Original generated project artwork; no game file copied'
    elif '/fonts/' in relative:
        source='https://github.com/google/fonts/tree/main/ofl/pressstart2p';version='Google Fonts main retrieved 2026-10-18';terms='SIL Open Font License 1.1; see web/assets/fonts/OFL.txt'
    else:
        source='Original project SVG';version='2026-10-18';terms='Project-authored replacement asset'
    files.append({'path':relative,'source':source,'version':version,'usage':terms,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
manifest={'schema_version':1,'reference':'https://datathon.com.kz/ru','reference_usage':'Visual reference only; no source code or assets copied',
          'files':files,'inline_assets':[{'path':'web/index.html','purpose':'Original pixel icons and sad ghast SVG'},{'path':'web/audio.js','purpose':'Quiet original procedural UI sound effects; no music'}],
          'private_minecraft_pack':{'path':'private_asset_pack/minecraft/1.21.10/manifest.json','enabled_by_default':False,'public_redistribution_approved':False,'excluded_from_docker_and_git':True},
          'generation_prompts':'ASSETS.md','music':{'provided':False,'generated':False,'enabled':False,'slots':['web/assets/music/overworld.ogg','web/assets/music/nether.ogg']}}
(root/'ASSET_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('asset_manifest_written',len(files),'files')
