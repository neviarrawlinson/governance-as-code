"""Preview and prepare explicitly authorized recovery; no GitHub writes."""
import argparse
from datetime import date, datetime, timezone
from pathlib import Path
from shutil import copyfile

from automation.recovery import (build_recovery_candidate, verify_recovery_preview,
 validate_recovery_authorization, build_recovery_receipt, read_json, write_json, sha256_file)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='mode',required=True)
    preview=sub.add_parser('preview')
    preview.add_argument('--evaluation-date',type=date.fromisoformat,required=True)
    preview.add_argument('--output-directory',type=Path,required=True)
    prepare=sub.add_parser('prepare')
    for flag in ['preview-directory','authorization','output-directory']:
        prepare.add_argument('--'+flag,type=Path,required=True)
    for flag in ['repository','branch','actor','authorization-commit','promotion-run-id','preview-run-id','preview-artifact-id']:
        prepare.add_argument('--'+flag,required=True)
    args=parser.parse_args()
    today=datetime.now(timezone.utc).date()
    if args.mode=='preview':
        if args.evaluation_date>today:raise ValueError('Future evaluation date')
        manifest=build_recovery_candidate(args.evaluation_date,args.output_directory)
        print('Preview only; no authoritative publication or issue operations.')
        print('Candidate SHA-256: '+manifest['candidate_sha256'])
        print('Manifest SHA-256: '+sha256_file(args.output_directory/'recovery-manifest.json'))
        return
    manifest=verify_recovery_preview(args.preview_directory,today=today)
    authorization=read_json(args.authorization)
    validate_recovery_authorization(authorization,manifest,repository=args.repository,branch=args.branch,
        actor=args.actor,today=today,manifest_sha256=sha256_file(args.preview_directory/'recovery-manifest.json'))
    if authorization['preview_run_id']!=args.preview_run_id or authorization['preview_artifact_id']!=args.preview_artifact_id:
        raise ValueError('Authorization preview IDs do not match downloaded preview')
    receipt=build_recovery_receipt(authorization,manifest,promotion_run_id=args.promotion_run_id,
        authorization_commit=args.authorization_commit,actor=args.actor)
    args.output_directory.mkdir(parents=True,exist_ok=True)
    if any(args.output_directory.iterdir()):raise ValueError('Publication directory must be empty')
    copyfile(args.preview_directory/'trusted-assurance-state.json',args.output_directory/'trusted-assurance-state.json')
    write_json(args.output_directory/'recovery-receipt.json',receipt)
    print('Validated publication inputs prepared; no GitHub writes performed.')

if __name__=='__main__':main()
