"""GitHub read-only admission and freshness checks for manual recovery."""
import argparse
import hashlib
import os
import re
from pathlib import Path

from automation.recovery import AUTH_KEYS, read_json, write_json, safe_relative, sha256_file
from automation.state import load_trusted_state
from automation.state_retrieval import (gh_json, gh_archive, extract_bounded_zip, RECOVERY_WORKFLOW,
    retrieve_trusted_state, check_candidate_freshness)


def authorization_path(root: Path, value: str) -> Path:
    if not safe_relative(value):raise ValueError('Unsafe authorization path')
    allowed=(root/'examples/machine-readable-control/recovery').resolve()
    path=root/value
    if path.is_symlink() or not path.resolve().is_relative_to(allowed) or path.suffix!='.json' or not path.is_file():
        raise ValueError('Authorization must be a JSON file within the reviewed recovery directory')
    return path


def validate_preview_source(approval: dict, run: dict, artifact: dict, *, branch: str) -> None:
    if (str(run['id'])!=approval['preview_run_id'] or run.get('status')!='completed' or run.get('conclusion')!='success'
        or run.get('head_branch')!=branch or run.get('head_sha')!=approval['source_commit']
        or run.get('path','').split('@')[0]!=RECOVERY_WORKFLOW or run.get('event')!='workflow_dispatch'
        or not run.get('repository',{}).get('id') or run.get('head_repository',{}).get('id')!=run['repository']['id']):
        raise ValueError('Preview workflow source is ineligible')
    if (str(artifact['id'])!=approval['preview_artifact_id'] or artifact.get('expired')
        or artifact.get('name')!='synthetic-history-recovery-preview-'+approval['preview_run_id']
        or str(artifact.get('workflow_run',{}).get('id'))!=approval['preview_run_id']
        or artifact['workflow_run'].get('head_sha')!=approval['source_commit'] or artifact['workflow_run'].get('head_branch')!=branch):
        raise ValueError('Preview artifact source is ineligible')


def _output(name: str, value: str):
    if '\n' in value or '\r' in value:raise ValueError('Invalid workflow output')
    output=os.environ.get('GITHUB_OUTPUT')
    if output:
        with Path(output).open('a') as stream:stream.write(name+'='+value+'\n')


def download_preview(repository: str, branch: str, approval: dict, destination: Path) -> None:
    for key in ('preview_run_id','preview_artifact_id'):
        if not re.fullmatch('[0-9]+',str(approval.get(key,''))):raise ValueError('Invalid preview IDs')
    run=gh_json(f'repos/{repository}/actions/runs/{approval["preview_run_id"]}')
    artifact=gh_json(f'repos/{repository}/actions/artifacts/{approval["preview_artifact_id"]}')
    validate_preview_source(approval,run,artifact,branch=branch)
    data=gh_archive(f'repos/{repository}/actions/artifacts/{artifact["id"]}/zip')
    if artifact.get('digest')!='sha256:'+hashlib.sha256(data).hexdigest():raise ValueError('Preview archive digest mismatch')
    extract_bounded_zip(data,destination)


def publication_ready(repository: str, branch: str, current_run_id: str, publication: Path, prior_directory: Path) -> bool:
    candidate=read_json(publication/'recovery-receipt.json')
    # Partial retries cannot overwrite an already uploaded current-run artifact.
    prior_uploads=gh_json(f'repos/{repository}/actions/runs/{current_run_id}/artifacts?per_page=100')['artifacts']
    for artifact in prior_uploads:
        if artifact.get('name')!='trusted-assurance-state':continue
        if artifact.get('expired'):raise ValueError('Prior recovery upload expired; create a new reviewed preview')
        data=gh_archive(f'repos/{repository}/actions/artifacts/{artifact["id"]}/zip')
        if artifact.get('digest')!='sha256:'+hashlib.sha256(data).hexdigest():raise ValueError('Prior recovery upload digest mismatch')
        retry_directory=prior_directory/'retry';extract_bounded_zip(data,retry_directory)
        if read_json(retry_directory/'recovery-receipt.json')!=candidate or sha256_file(retry_directory/'trusted-assurance-state.json')!=candidate['manifest']['candidate_sha256']:
            raise ValueError('Existing recovery upload conflicts with approved publication')
        return False
    metadata=retrieve_trusted_state(repository,branch,current_run_id,prior_directory/'baseline')
    if metadata['status'] in {'ABSENT','EXPIRED'}:return True
    if metadata['status']!='FOUND':raise ValueError('Cannot establish baseline freshness: '+metadata['reason'])
    previous=load_trusted_state(prior_directory/'baseline/trusted-assurance-state.json','ACP-001-03')
    return check_candidate_freshness(candidate['manifest'],dict(evaluation_date=previous['evaluation_date'],
        candidate_sha256=sha256_file(prior_directory/'baseline/trusted-assurance-state.json')))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='mode',required=True)
    admission=sub.add_parser('download-preview')
    admission.add_argument('--root',type=Path,required=True)
    admission.add_argument('--authorization-path',required=True)
    admission.add_argument('--authorization-copy',type=Path,required=True)
    admission.add_argument('--destination',type=Path,required=True)
    admission.add_argument('--preview-run-id',required=True)
    admission.add_argument('--preview-artifact-id',required=True)
    admission.add_argument('--actor',required=True)
    admission.add_argument('--commit',required=True)
    freshness=sub.add_parser('freshness')
    freshness.add_argument('--publication',type=Path,required=True)
    freshness.add_argument('--prior-directory',type=Path,required=True)
    freshness.add_argument('--current-run-id',required=True)
    for p in (admission,freshness):
        p.add_argument('--repository',required=True);p.add_argument('--branch',required=True)
    args=parser.parse_args()
    if not re.fullmatch('[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',args.repository) or args.branch!='main':raise ValueError('Recovery is restricted to the repository main branch')
    if args.mode=='freshness':
        ready=publication_ready(args.repository,args.branch,args.current_run_id,args.publication,args.prior_directory)
        _output('ready',str(ready).lower());print('Publication ready.' if ready else 'Matching authoritative publication already exists; no upload.')
        return
    default=gh_json(f'repos/{args.repository}')['default_branch']
    head=gh_json(f'repos/{args.repository}/commits/main')['sha']
    if default!='main' or head!=args.commit:raise ValueError('Promotion requires current default-branch authorization commit')
    approval=read_json(authorization_path(args.root,args.authorization_path))
    if set(approval)!=AUTH_KEYS or approval.get('repository')!=args.repository or approval.get('branch')!=args.branch or approval.get('approver')!=args.actor:
        raise ValueError('Authorization identity mismatch')
    if approval.get('preview_run_id')!=args.preview_run_id or approval.get('preview_artifact_id')!=args.preview_artifact_id or not re.fullmatch('[0-9a-f]{40}',str(approval.get('source_commit',''))):
        raise ValueError('Authorization does not match dispatched preview')
    download_preview(args.repository,args.branch,approval,args.destination)
    args.authorization_copy.parent.mkdir(parents=True,exist_ok=True);write_json(args.authorization_copy,approval)
    _output('source_commit',approval['source_commit'])

if __name__=='__main__':main()
