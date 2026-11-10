"""Package only repository-owned files; never walk browser or backup folders."""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def version():
    text=(ROOT/'wxbackup'/'__init__.py').read_text('utf-8')
    match=re.search(r"__version__\s*=\s*['\"]([^'\"]+)",text)
    if not match: raise RuntimeError('Version missing')
    return match.group(1)


def source_files():
    names=['main.py','README.md','LICENSE','THIRD_PARTY_NOTICES.md','CHANGELOG.md',
           'CONTRIBUTING.md','SECURITY.md','RELEASE_NOTES.md','.gitignore','.gitattributes',
           'pyproject.toml','requirements.txt','requirements-dev.txt','setup.cmd','build.cmd','启动备份.cmd']
    files=[ROOT/name for name in names]
    for folder,suffixes in [('wxbackup',{'.py'}),('tests',{'.py'}),('scripts',{'.py'}),
                            ('docs',{'.md','.txt','.rst'}),('.github',{'.md','.yml','.yaml'})]:
        files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in suffixes and '__pycache__' not in p.parts)
    for path in files:
        if not path.is_file(): raise FileNotFoundError(path)
    return sorted(set(files))


def write_archive(path,entries):
    temporary=path.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
        for source,target in entries: bundle.write(source,str(target).replace('\\','/'))
    with zipfile.ZipFile(temporary) as bundle:
        if bundle.testzip() is not None: raise RuntimeError('Archive integrity check failed')
    os.replace(temporary,path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,help='PyInstaller output directory containing WechatBackup.exe')
    parser.add_argument('--output',type=Path,default=ROOT/'release-assets')
    args=parser.parse_args()
    output=args.output.resolve(); output.mkdir(parents=True,exist_ok=True)
    current=version(); prefix=f'WechatBackup-v{current}'
    files=source_files()
    source=output/f'{prefix}-source.zip'
    write_archive(source,[(p,Path(prefix)/p.relative_to(ROOT)) for p in files])
    artifacts=[source]
    if args.runtime:
        runtime=args.runtime.resolve()
        if not (runtime/'WechatBackup.exe').is_file() or not (runtime/'_internal').is_dir():
            raise RuntimeError('Expected an onedir runtime with WechatBackup.exe and _internal')
        # Runtime must be a dedicated build output, not an existing user install.
        if (runtime/'data').exists() or (runtime/'备份').exists():
            raise RuntimeError('Refusing to package a runtime containing user data')
        entries=[(p,Path(prefix)/p.relative_to(ROOT)) for p in files]
        entries.extend((p,Path(prefix)/'runtime'/p.relative_to(runtime)) for p in runtime.rglob('*') if p.is_file())
        windows=output/f'{prefix}-windows-x64.zip'
        write_archive(windows,entries); artifacts.append(windows)
    sums=''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in artifacts)
    (output/'SHA256SUMS.txt').write_text(sums,encoding='ascii')
    for path in artifacts: print(f'{path.name}: {path.stat().st_size:,} bytes')


if __name__=='__main__': main()
