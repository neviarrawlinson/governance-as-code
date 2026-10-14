"""Retrieve eligible published state with bounded archives and recovery receipts."""
import argparse
import hashlib
import io
import json
import os
import stat
import selectors
import time
import subprocess
import zipfile
from datetime import date
from pathlib import Path

from automation.recovery import (read_json, write_json, safe_relative, validate_manifest,
    validate_recovery_authorization, sha256_file)
from automation.state import load_trusted_state

NORMAL_WORKFLOW='.github/workflows/governance-assurance.yml'
RECOVERY_WORKFLOW='.github/workflows/governance-history-recovery.yml'
LIMIT=10*1024*1024
DOWNLOAD_TIMEOUT=60
RECEIPT_KEYS={'schema_version','boundary_type','historical_interval_status','authorization','manifest','promotion_run_id','authorization_commit','executed_by'}


def _source_kind(run: dict, branch: str):
    path=run.get('path','').split('@')[0]
    if run.get('head_branch')!=branch or run.get('status')!='completed' or run.get('conclusion')!='success':return None
    if not run.get('repository',{}).get('id') or run.get('head_repository',{}).get('id')!=run['repository']['id']:return None
    if path==NORMAL_WORKFLOW:return 'NORMAL'
    if path==RECOVERY_WORKFLOW and run.get('event')=='workflow_dispatch':return 'RECOVERY'
    return None


def select_trusted_state(runs: list[dict], artifacts: list[dict], *, branch: str, current_run_id: str):
    by_id={str(r['id']):r for r in runs}
    eligible=[]
    for artifact in artifacts:
        rid=str(artifact.get('workflow_run',{}).get('id',''))
        run=by_id.get(rid)
        if artifact.get('name')!='trusted-assurance-state' or artifact.get('expired') or rid==str(current_run_id) or not run:continue
        kind=_source_kind(run,branch)
        if kind and artifact.get('workflow_run',{}).get('head_branch')==branch and artifact['workflow_run'].get('head_sha')==run.get('head_sha'):
            eligible.append(dict(artifact=artifact,source_run=run,source_kind=kind))
    return max(eligible,key=lambda item:(item['artifact']['created_at'],item['artifact']['id']),default=None)


def extract_bounded_zip(data: bytes, destination: Path) -> None:
    if len(data)>LIMIT:raise ValueError('Artifact archive exceeds size limit')
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries=archive.infolist();names=set()
            if len(entries)>1000 or sum(x.file_size for x in entries)>LIMIT:raise ValueError('Artifact expanded size exceeds limit')
            for item in entries:
                name=item.filename.rstrip('/') if item.is_dir() else item.filename
                if not safe_relative(name) or name in names or stat.S_ISLNK(item.external_attr>>16):raise ValueError('Unsafe archive path')
                names.add(name)
            destination.mkdir(parents=True,exist_ok=True)
            if any(destination.iterdir()):raise ValueError('Extraction directory must be empty')
            for item in entries:
                target=destination/item.filename
                if item.is_dir():target.mkdir(parents=True,exist_ok=True)
                else:
                    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(item))
    except (zipfile.BadZipFile,RuntimeError,OSError) as exc:raise ValueError('Invalid artifact archive') from exc


def validate_recovery_source(receipt: dict, state_path: Path, *, source_run: dict, artifact: dict,
    expected_repository: str, expected_branch: str) -> None:
    if not isinstance(receipt,dict) or set(receipt)!=RECEIPT_KEYS or receipt['schema_version']!='1.0' or receipt['boundary_type']!='EXPLICIT_REBASELINE' or receipt['historical_interval_status']!='UNKNOWN':raise ValueError('Invalid recovery receipt')
    if _source_kind(source_run,expected_branch)!='RECOVERY' or str(source_run['id'])!=receipt['promotion_run_id'] or str(artifact.get('workflow_run',{}).get('id'))!=receipt['promotion_run_id'] or source_run.get('head_sha')!=receipt['authorization_commit']:raise ValueError('Recovery receipt does not match API source')
    actor=source_run.get('triggering_actor',source_run.get('actor',{})).get('login')
    if actor!=receipt['executed_by']:raise ValueError('Recovery actor mismatch')
    manifest=receipt['manifest'];validate_manifest(manifest)
    manifest_bytes=(json.dumps(manifest,indent=2,sort_keys=True)+'\n').encode()
    authorization=receipt['authorization']
    promotion_date=date.fromisoformat(artifact['created_at'][:10])
    validate_recovery_authorization(authorization,manifest,repository=expected_repository,branch=expected_branch,actor=actor,
        today=promotion_date,manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest())
    if sha256_file(state_path)!=manifest['candidate_sha256']:raise ValueError('Recovery state checksum mismatch')
    state=load_trusted_state(state_path,manifest['control_id'],promotion_date)
    if state['evaluation_date']!=manifest['evaluation_date'] or {s['subject_id']:s['governance_outcome'] for s in state['subjects']}.get('USR-004')!='FAIL':raise ValueError('Recovery state does not preserve failure')


def check_candidate_freshness(candidate: dict, previous: dict | None) -> bool:
    if previous is None:return True
    current_date=date.fromisoformat(candidate['evaluation_date']);prior_date=date.fromisoformat(previous['evaluation_date'])
    if prior_date>current_date:raise ValueError('Newer authoritative baseline exists; preview again')
    if prior_date==current_date:
        if previous['candidate_sha256']!=candidate['candidate_sha256']:raise ValueError('Conflicting same-date baseline; preview again')
        return False
    return True


def gh_json(endpoint: str, *, paginate=False):
    args=['gh','api',endpoint]
    if paginate:args+=['--paginate','--slurp']
    completed=subprocess.run(args,check=True,capture_output=True,timeout=60)
    return json.loads(completed.stdout)


def gh_archive(endpoint: str) -> bytes:
    # A deadline covers both pipe reads and process termination, not only wait().
    deadline=time.monotonic()+DOWNLOAD_TIMEOUT
    with subprocess.Popen(['gh','api',endpoint], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
        try:
            data=bytearray()
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining=deadline-time.monotonic()
                    if remaining<=0 or not selector.select(remaining):
                        raise ValueError('Artifact download timed out')
                    chunk=os.read(process.stdout.fileno(),min(65536,LIMIT+1-len(data)))
                    if not chunk:break
                    data.extend(chunk)
                    if len(data)>LIMIT:raise ValueError('Downloaded artifact exceeds limit')
            remaining=deadline-time.monotonic()
            if remaining<=0:raise ValueError('Artifact download timed out')
            try:status=process.wait(timeout=remaining)
            except subprocess.TimeoutExpired as exc:raise ValueError('Artifact download timed out') from exc
            if status:raise ValueError('Artifact download failed')
            return bytes(data)
        except Exception:
            if process.poll() is None:process.kill()
            process.wait()
            raise


def retrieve_trusted_state(repository: str, branch: str, current_run_id: str, destination: Path) -> dict:
    metadata=dict(status='UNAVAILABLE',reason='Trusted-state retrieval unavailable.')
    try:
        pages=gh_json(f'repos/{repository}/actions/runs?branch={branch}&per_page=100',paginate=True)
        runs=[r for page in pages for r in page['workflow_runs']]
        pages=gh_json(f'repos/{repository}/actions/artifacts?name=trusted-assurance-state&per_page=100',paginate=True)
        artifacts=[a for page in pages for a in page['artifacts']]
    except (OSError,ValueError,KeyError,subprocess.SubprocessError):
        return dict(metadata,failure_stage='API_RETRIEVAL')
    choice=select_trusted_state(runs,artifacts,branch=branch,current_run_id=current_run_id)
    if choice is None:
        status='EXPIRED' if any(a.get('expired') for a in artifacts) else ('INELIGIBLE' if artifacts else 'ABSENT')
        return dict(status=status,reason='No active eligible trusted assurance state is available.')
    artifact=choice['artifact'];run=choice['source_run'];kind=choice['source_kind']
    source=dict(source_run_id=str(run['id']),artifact_id=str(artifact['id']),artifact_name=artifact['name'],source_kind=kind)
    try:
        data=gh_archive(f'repos/{repository}/actions/artifacts/{artifact["id"]}/zip')
        digest=artifact.get('digest')
        if kind=='RECOVERY' and not digest:raise ValueError('Recovery artifact requires API digest')
        if digest and digest!='sha256:'+hashlib.sha256(data).hexdigest():raise ValueError('Artifact digest mismatch')
        extract_bounded_zip(data,destination)
        files={p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()}
        expected={'trusted-assurance-state.json'}|({'recovery-receipt.json'} if kind=='RECOVERY' else set())
        if files!=expected:raise ValueError('Authoritative artifact has unexpected contents')
        if kind=='RECOVERY':
            validate_recovery_source(read_json(destination/'recovery-receipt.json'),destination/'trusted-assurance-state.json',
                source_run=run,artifact=artifact,expected_repository=repository,expected_branch=branch)
        load_trusted_state(destination/'trusted-assurance-state.json','ACP-001-03',date.today())
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as exc:
        return dict(source,status='INVALID',failure_stage='ARTIFACT_VALIDATION',reason=str(exc))
    return dict(source,status='FOUND',reason='Eligible authoritative state downloaded and validated.',
        recovery_receipt_verified=kind=='RECOVERY')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['repository','branch','current-run-id']:parser.add_argument('--'+name,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--metadata',type=Path,required=True)
    args=parser.parse_args()
    metadata=retrieve_trusted_state(args.repository,args.branch,args.current_run_id,args.destination)
    args.metadata.parent.mkdir(parents=True,exist_ok=True);write_json(args.metadata,metadata)
    output=os.environ.get('GITHUB_OUTPUT')
    if output:
        with Path(output).open('a') as stream:stream.write('path='+ (str(args.destination/'trusted-assurance-state.json') if metadata['status']=='FOUND' else '')+'\n')
    print(metadata['reason'])

if __name__=='__main__':main()
