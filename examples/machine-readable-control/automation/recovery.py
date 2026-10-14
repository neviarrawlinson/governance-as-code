"""Explicit current-state recovery. This module never performs issue operations."""
import hashlib
import json
import re
from datetime import date
from pathlib import Path, PurePosixPath

from automation.pipeline import (CONTROL_PATH, ENVIRONMENT_PATH, VALIDATOR_PATH,
    REPOSITORY_ROOT, prepare_pipeline, complete_pipeline)
from automation.state import load_trusted_state
from evidence.integrity import sha256_file, verify_evidence, get_repository_commit, VERIFIED

AUTH_KEYS = {'schema_version','recovery_id','repository','branch','control_id','preview_run_id',
 'preview_artifact_id','source_commit','evaluation_date','candidate_sha256','manifest_sha256',
 'approver','approved_at','valid_until','reason','history_gap_acknowledged','review_mode','related_issue'}
MANIFEST_KEYS = {'schema_version','boundary_type','source_commit','control_id','evaluation_date','candidate_sha256','files'}


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n', encoding='utf-8')


def safe_relative(name: str) -> bool:
    return isinstance(name,str) and bool(name) and '\\' not in name and not name.startswith('/') and all(x not in ('','..','.') for x in name.split('/')) and not PurePosixPath(name).is_absolute()


def read_json(path: Path) -> dict:
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f'Invalid JSON file: {path.name}') from exc
    if not isinstance(value,dict):
        raise ValueError(f'Expected object: {path.name}')
    return value


def build_recovery_candidate(evaluation_date: date, output_directory: Path) -> dict:
    output_directory.mkdir(parents=True,exist_ok=True)
    if any(output_directory.iterdir()):
        raise ValueError('Preview output directory must be empty')
    source_commit=get_repository_commit(REPOSITORY_ROOT)
    if not source_commit:
        raise ValueError('Recovery requires Git commit provenance')
    prepared=prepare_pipeline(evaluation_date,output_directory)
    result=complete_pipeline(prepared,historical_comparison_allowed=False,candidate_state_allowed=True)
    if not result.succeeded or result.events or any(d.transition is not None for d in result.decisions):
        raise ValueError('Recovery preview requires verified evidence and no history-dependent events')
    if {d.subject_id:d.governance_outcome for d in result.decisions}.get('USR-004') != 'FAIL':
        raise ValueError('Recover history before remediating USR-004')
    manifest=dict(schema_version='1.0',boundary_type='EXPLICIT_REBASELINE',source_commit=source_commit,
        control_id=prepared.control['control']['id'],evaluation_date=evaluation_date.isoformat(),
        candidate_sha256=sha256_file(output_directory/'trusted-assurance-state.json'),
        files={p.relative_to(output_directory).as_posix():sha256_file(p) for p in sorted(output_directory.rglob('*')) if p.is_file()})
    write_json(output_directory/'recovery-manifest.json',manifest)
    return manifest


def validate_manifest(manifest: dict) -> None:
    if set(manifest)!=MANIFEST_KEYS or manifest.get('schema_version')!='1.0' or manifest.get('boundary_type')!='EXPLICIT_REBASELINE':
        raise ValueError('Invalid recovery manifest')
    if not re.fullmatch('[0-9a-f]{40}',str(manifest['source_commit'])) or manifest['control_id']!='ACP-001-03':
        raise ValueError('Invalid recovery source or control')
    if not isinstance(manifest['files'],dict) or not manifest['files']:
        raise ValueError('Empty manifest file inventory')
    if any(not safe_relative(n) or not isinstance(d,str) or not re.fullmatch('[0-9a-f]{64}',d) for n,d in manifest['files'].items()):
        raise ValueError('Invalid manifest path or checksum')
    if manifest['files'].get('trusted-assurance-state.json')!=manifest['candidate_sha256']:
        raise ValueError('Manifest candidate checksum inconsistent')
    try:date.fromisoformat(manifest['evaluation_date'])
    except (ValueError,TypeError) as exc:raise ValueError('Invalid evaluation date') from exc


def verify_recovery_preview(directory: Path, *, today: date) -> dict:
    manifest=read_json(directory/'recovery-manifest.json');validate_manifest(manifest)
    if date.fromisoformat(manifest['evaluation_date'])>today:
        raise ValueError('Future evaluation date')
    if get_repository_commit(REPOSITORY_ROOT)!=manifest['source_commit']:
        raise ValueError('Check out the exact preview source commit for verification')
    actual={p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
    if actual!=set(manifest['files'])|{'recovery-manifest.json'}:
        raise ValueError('Preview file inventory mismatch')
    for name,digest in manifest['files'].items():
        p=directory/name
        if p.is_symlink() or sha256_file(p)!=digest:
            raise ValueError('Preview file checksum mismatch')
    state=load_trusted_state(directory/'trusted-assurance-state.json',manifest['control_id'],today)
    if state['evaluation_date']!=manifest['evaluation_date'] or {s['subject_id']:s['governance_outcome'] for s in state['subjects']}.get('USR-004')!='FAIL':
        raise ValueError('Recovery candidate does not preserve current failure')
    decisions=json.loads((directory/'assurance-decisions.json').read_text())
    if not isinstance(decisions,list) or not decisions or any(d.get('transition') is not None or d.get('integrity_status')!='VERIFIED' or d.get('evaluation_date')!=state['evaluation_date'] or d.get('control_id')!=state['control_id'] for d in decisions):
        raise ValueError('Invalid recovery decisions')
    if any((directory/'events').glob('*.json')):
        raise ValueError('Recovery must not generate events')
    expected={s['subject_id']:s['governance_outcome'] for s in state['subjects']}
    observed={}
    for p in (directory/'evidence').glob('*.json'):
        record=read_json(p)
        if verify_evidence(p,p.with_suffix('.json.sha256'),CONTROL_PATH,ENVIRONMENT_PATH,VALIDATOR_PATH).status!=VERIFIED:
            raise ValueError('Evidence does not verify against pinned source')
        sid=record['subject']['account_id']
        if sid in observed or record['evaluation']['evaluation_date']!=manifest['evaluation_date'] or record['provenance'].get('repository_commit')!=manifest['source_commit'] or record['control']['id']!=state['control_id']:
            raise ValueError('Evidence identity or provenance mismatch')
        observed[sid]=record['result']['outcome']
    if observed!=expected or {d['subject_id']:d['governance_outcome'] for d in decisions}!=expected or len(decisions)!=len(expected):
        raise ValueError('Candidate outcomes do not match evidence')
    return manifest


def validate_recovery_authorization(authorization: dict, manifest: dict, *, repository: str, branch: str,
    actor: str, today: date, manifest_sha256: str) -> None:
    if not isinstance(authorization,dict) or set(authorization)!=AUTH_KEYS:
        raise ValueError('Missing or unexpected authorization fields')
    for key in AUTH_KEYS-{'history_gap_acknowledged','related_issue'}:
        if not isinstance(authorization[key],str) or not authorization[key].strip():
            raise ValueError(f'Invalid authorization field: {key}')
    if authorization['schema_version']!='1.0' or authorization['review_mode'] not in {'independent','disclosed_self_review'} or authorization['history_gap_acknowledged'] is not True or type(authorization['related_issue']) is not int or authorization['related_issue']!=3:
        raise ValueError('Authorization must acknowledge scope, review and unknown history')
    if authorization['repository']!=repository or authorization['branch']!=branch or authorization['approver']!=actor:
        raise ValueError('Authorization does not match repository, branch or actor')
    for key in ['source_commit','evaluation_date','control_id','candidate_sha256']:
        if authorization[key]!=manifest[key]:raise ValueError(f'Authorization mismatch: {key}')
    if authorization['manifest_sha256']!=manifest_sha256:
        raise ValueError('Authorization manifest checksum mismatch')
    if any(not re.fullmatch('[0-9]+',authorization[k]) for k in ['preview_run_id','preview_artifact_id']):
        raise ValueError('Preview IDs must be numeric strings')
    try:
        approved=date.fromisoformat(authorization['approved_at']);valid=date.fromisoformat(authorization['valid_until']);evaluated=date.fromisoformat(manifest['evaluation_date'])
    except (ValueError,TypeError) as exc:raise ValueError('Invalid authorization dates') from exc
    if not evaluated<=approved<=today<=valid:
        raise ValueError('Authorization is future, stale or predates evaluation')


def build_recovery_receipt(authorization: dict, manifest: dict, *, promotion_run_id: str,
    authorization_commit: str, actor: str) -> dict:
    if not re.fullmatch('[0-9]+',promotion_run_id) or not re.fullmatch('[0-9a-f]{40}',authorization_commit):
        raise ValueError('Invalid promotion provenance')
    return dict(schema_version='1.0',boundary_type='EXPLICIT_REBASELINE',historical_interval_status='UNKNOWN',
        authorization=authorization,manifest=manifest,promotion_run_id=promotion_run_id,
        authorization_commit=authorization_commit,executed_by=actor)
