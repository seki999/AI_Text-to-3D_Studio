"""Generate explicit per-user MSI components with HKCU registry key paths."""
import hashlib,sys,uuid,xml.etree.ElementTree as ET
from pathlib import Path
root=Path(__file__).resolve().parents[1];payload=root/'release'/'FormaStudio';output=root/'release'/'FormaStudio.wxs'
ns='http://wixtoolset.org/schemas/v4/wxs';ET.register_namespace('',ns)
def element(parent,name,**attrs):return ET.SubElement(parent,'{'+ns+'}'+name,attrs)
wix=ET.Element('{'+ns+'}Wix');package=element(wix,'Package',Name='FORMA AI 3D Studio',Manufacturer='FORMA Project',Version='0.4.0',UpgradeCode='7A1249A4-7E22-4B04-980A-B109C4C00A04',Scope='perUser',Language='1033')
element(package,'MajorUpgrade',DowngradeErrorMessage='A newer FORMA version is already installed.')
element(package,'MediaTemplate',EmbedCab='yes',CompressionLevel='high')
standard=element(package,'StandardDirectory',Id='LocalAppDataFolder');programs=element(standard,'Directory',Id='UserPrograms',Name='Programs');install=element(programs,'Directory',Id='INSTALLFOLDER',Name='FORMA AI 3D Studio')
directories={Path('.'):install};components=[];main_file=None
for path in sorted(payload.rglob('*')):
    relative=path.relative_to(payload);key=hashlib.sha256(relative.as_posix().encode()).hexdigest()[:24]
    if path.is_dir():directories[relative]=element(directories[relative.parent],'Directory',Id='D'+key,Name=path.name);continue
    component=element(directories[relative.parent],'Component',Id='C'+key,Guid=str(uuid.uuid5(uuid.NAMESPACE_URL,'forma-v04/'+relative.as_posix())))
    element(component,'RegistryValue',Root='HKCU',Key='Software\\FORMAStudio\\Components',Name=key,Type='integer',Value='1',KeyPath='yes')
    file=element(component,'File',Id='F'+key,Source=str(path),Name=path.name)
    if relative.as_posix()=='FormaStudio.exe':main_file=file.attrib['Id']
    components.append(component.attrib['Id'])
menu=element(package,'StandardDirectory',Id='ProgramMenuFolder');brand=element(menu,'Directory',Id='FormaMenu',Name='FORMA AI 3D Studio')
component=element(brand,'Component',Id='MenuShortcut',Guid='248b6884-a3c6-43fe-8c1d-03124876dd63')
element(component,'Shortcut',Id='StartMenuShortcut',Name='FORMA AI 3D Studio',Target='[#'+str(main_file)+']',WorkingDirectory='INSTALLFOLDER')
element(component,'RemoveFolder',Id='RemoveFormaMenu',On='uninstall')
element(component,'RegistryValue',Root='HKCU',Key='Software\\FORMAStudio',Name='Installed',Type='integer',Value='1',KeyPath='yes');components.append('MenuShortcut')
feature=element(package,'Feature',Id='Complete',Title='FORMA Studio',Level='1')
for id in components:element(feature,'ComponentRef',Id=id)
ET.indent(wix);ET.ElementTree(wix).write(output,encoding='utf-8',xml_declaration=True)
print(output)
