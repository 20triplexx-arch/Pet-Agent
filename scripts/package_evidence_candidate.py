"""Local, unactivated source candidate. Excludes all runtime/user/eval data."""
import hashlib
import json
import sys
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from package_source import source_files

ROOT=Path(__file__).resolve().parents[1]


def main():
    acceptance=json.loads((ROOT/'docs/evidence-acceptance-20261019.json').read_text(encoding='utf-8'))
    build=acceptance['answer_build_sha256']
    target=ROOT/'artifacts'/f'chongban-evidence-20261019-{build[:12]}.zip'
    files=sorted({p for p in source_files() if '.impeccable' not in p.parts})
    hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    # Exclusive creation prevents accidental replacement of a prior delivery.
    with ZipFile(target,'x',compression=ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path,path.relative_to(ROOT).as_posix())
        archive.writestr('EVIDENCE_CANDIDATE.json',json.dumps({
            'answer_build_sha256':build,'activated':False,'releasable':acceptance['releasable'],
            'source_only':True,'files':hashes,
            'excluded':['credentials','runtime storage','business databases','browser profiles',
                        'evaluation wire captures','historical screenshots','node_modules','build outputs'],
            'rollback_source':'artifacts/evidence-rebuild/baseline.zip; Git 9520744',
        },ensure_ascii=False,indent=2)+'\n')
    with ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('Candidate archive integrity failed')
        for name,checksum in hashes.items():
            if hashlib.sha256(archive.read(name)).hexdigest()!=checksum:
                raise RuntimeError('Source manifest mismatch: '+name)
        forbidden=('/storage/','/node_modules/','/artifacts/','.env.local','/.env','-wire.json')
        if any(any(part in '/'+name for part in forbidden) for name in archive.namelist() if name!='.env.example'):
            raise RuntimeError('Disallowed runtime or private path')
    info={'path':target.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
          'files':len(hashes)+1,'bytes':target.stat().st_size,'releasable':False,'activated':False}
    (target.with_suffix('.json')).write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(info,ensure_ascii=False))


if __name__=='__main__':
    main()
