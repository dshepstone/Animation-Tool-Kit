"""Build and verify a portable release ZIP from the canonical source tree.

Usage: python package_atk_release.py --version 1.1.10 [--sync-dist]
The Python packager complements the existing PowerShell packager for CI.
"""
import argparse
import hashlib
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
FILES = ['ATK_LICENSE.md', 'README.md', 'THIRD_PARTY_NOTICES.md', 'install_atk_toolbar.mel']
FOLDERS = ['animation tool kit scripts', 'atk_toolbar']


def release_files(version):
    paths = [ROOT / name for name in FILES]
    paths.append(ROOT / ('Animation_Tool_Kit_v%s_Release_Notes.md' % version))
    for folder in FOLDERS:
        paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file())
    return sorted(p for p in paths if not any(part in ('__pycache__','.git') for part in p.parts)
                  and p.suffix not in ('.pyc','.pyo') and p.name not in ('.DS_Store','Thumbs.db'))


def build(version, sync_dist=False):
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Expected a semantic version such as 1.1.10')
    text = (ROOT/'atk_toolbar/__init__.py').read_text(encoding='utf-8')
    if '__version__ = "%s"' % version not in text:
        raise ValueError('Requested version does not match the toolkit')
    paths = release_files(version)
    dist = ROOT/'dist'
    dist.mkdir(exist_ok=True)
    target = dist/('AnimationToolKit_v%s.zip' % version.replace('.','_'))
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            name = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            archive.writestr(name, data)
            if sync_dist:
                destination = dist/name
                destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes(data)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP CRC validation failed')
        for path in paths:
            name = path.relative_to(ROOT).as_posix()
            if archive.read(name) != path.read_bytes():
                raise ValueError('ZIP content mismatch: '+name)
        assert all('\\' not in name and not name.startswith('/') and '..' not in name.split('/') for name in archive.namelist())
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(digest+'  '+target.name+'\n',encoding='utf-8')
    print('%s: %d verified files, SHA-256 %s' % (target,len(paths),digest))
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version',required=True)
    parser.add_argument('--sync-dist',action='store_true')
    args=parser.parse_args()
    build(args.version,args.sync_dist)
