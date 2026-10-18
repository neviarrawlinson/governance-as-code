"""Observe scheduled assurance health without changing control or trusted state."""
import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
from urllib.parse import urlencode

WORKFLOW = '.github/workflows/governance-assurance.yml'
MARKER = '<!-- gac-assurance-monitor:v1 -->'
START = '<!-- gac-monitor-status:start -->'
END = '<!-- gac-monitor-status:end -->'
MAX_AGE = timedelta(days=8)


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone is required')
    return result


def assess(runs, *, repository, now):
    scheduled = [r for r in runs if
                 r.get('path', '').split('@')[0] == WORKFLOW
                 and r.get('head_branch') == 'main'
                 and r.get('event') == 'schedule'
                 and r.get('repository', {}).get('full_name') == repository
                 and r.get('head_repository', {}).get('id') == r.get('repository', {}).get('id')
                 and r.get('repository', {}).get('id')
                 and timestamp(r['created_at']) <= now]
    scheduled.sort(key=lambda r: (timestamp(r['created_at']), r['id']), reverse=True)
    latest = scheduled[0] if scheduled else None
    success = next((r for r in scheduled if r.get('status') == 'completed'
                    and r.get('conclusion') == 'success'), None)
    problems = []
    if latest and latest.get('status') == 'completed' and latest.get('conclusion') != 'success':
        problems.append('LATEST_SCHEDULED_RUN_UNSUCCESSFUL')
    if success is None:
        problems.append('NO_SUCCESSFUL_SCHEDULED_RUN')
    elif now - timestamp(success['created_at']) > MAX_AGE:
        problems.append('SCHEDULED_SUCCESS_OLDER_THAN_8_DAYS')
    def evidence(run):
        if run is None:
            return None
        return {key: run.get(key) for key in ('id', 'created_at', 'status', 'conclusion', 'head_sha')}
    return {'schema_version': '1.0', 'repository': repository,
            'healthy': not problems, 'problems': problems,
            'latest_scheduled_run': evidence(latest), 'last_success': evidence(success)}


def api(endpoint, *, payload=None, method=None, paginate=False):
    args = ['gh', 'api', endpoint]
    if paginate:
        args += ['--paginate', '--slurp']
    if method:
        args += ['--method', method]
    if payload is not None:
        args += ['--input', '-']
    result = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                            text=True, capture_output=True, check=True, timeout=90)
    return json.loads(result.stdout)


def render(report):
    repository = report['repository']
    lines = ['## Scheduled assurance health', '',
             'Status: ' + ('HEALTHY' if report['healthy'] else 'HUMAN REVIEW REQUIRED'), '']
    for problem in report['problems']:
        lines.append('- ' + problem)
    for label, key in [('Latest scheduled run', 'latest_scheduled_run'),
                       ('Last successful scheduled run', 'last_success')]:
        run = report[key]
        if run:
            lines.append(f"- {label}: https://github.com/{repository}/actions/runs/{run['id']} "
                         f"({run['status']}, {run['conclusion']}; started {run['created_at']})")
        else:
            lines.append(f'- {label}: none observed')
    for item in report.get('failed_steps', []):
        lines.append(f"- Failed job/step: {item['job']} / {item['step']}")
    lines += ['', 'Owner: @neviarrawlinson. Review within one business day.',
              'Next action: inspect the linked run and failed steps; check scheduling and trusted-state availability. '
              'A manual success does not prove the weekly schedule is operating.',
              'When healthy, record the review decision and close this monitoring issue manually.',
              'This monitor does not authorize remediation, recover missing history, or modify control issues or trusted state.']
    return '\n'.join(lines) + '\n'


def synchronize(report, issues, *, live):
    """Maintain one monitor issue; preserve text outside the generated section."""
    matches = [i for i in issues if not i.get('pull_request')
               and MARKER in (i.get('body') or '')]
    if len(matches) > 1:
        raise ValueError('Multiple monitoring issues found; human reconciliation required')
    issue = matches[0] if matches else None
    if report['healthy'] and issue is None:
        return 'NO_ACTION'
    if report['healthy'] and issue.get('state') == 'closed':
        return 'NO_ACTION'
    fingerprint = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
    section = START + '\n' + render(report) + f'\n<!-- status-sha256:{fingerprint} -->\n' + END
    if issue is None:
        if live:
            api(f"repos/{report['repository']}/issues", method='POST', payload={
                'title': 'Scheduled governance assurance requires human review',
                'body': MARKER + '\n' + section + '\n\nHuman review notes:\n',
                'assignees': ['neviarrawlinson']})
        return 'CREATE_ISSUE'
    body = issue.get('body') or ''
    if body.count(START) != 1 or body.count(END) != 1 or body.index(START) >= body.index(END):
        raise ValueError('Monitoring status boundaries missing or invalid; preserve issue for human review')
    if f'<!-- status-sha256:{fingerprint} -->' in body and issue.get('state') == 'open':
        return 'NO_ACTION'
    updated = body[:body.index(START)] + section + body[body.index(END) + len(END):]
    if live:
        api(f"repos/{report['repository']}/issues/{issue['number']}", method='PATCH',
            payload={'body': updated, 'state': 'open'})
    return 'UPDATE_ISSUE' if issue.get('state') == 'open' else 'REOPEN_ISSUE'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('generated-monitoring/report.json'))
    args = parser.parse_args()
    repository = os.environ['GITHUB_REPOSITORY']
    event = os.environ.get('GITHUB_EVENT_NAME')
    if args.live and (os.environ.get('GITHUB_REF') != 'refs/heads/main'
                      or event not in ('workflow_dispatch', 'workflow_run', 'schedule')):
        raise SystemExit('Live monitoring requires an authorized main-branch workflow trigger')
    endpoint = f'repos/{repository}/actions/workflows/governance-assurance.yml/runs?'
    pages = api(endpoint + urlencode({'branch': 'main', 'event': 'schedule', 'per_page': 100}), paginate=True)
    report = assess([run for page in pages for run in page['workflow_runs']],
                    repository=repository, now=datetime.now(timezone.utc))
    latest = report['latest_scheduled_run']
    if latest and 'LATEST_SCHEDULED_RUN_UNSUCCESSFUL' in report['problems']:
        pages = api(f"repos/{repository}/actions/runs/{latest['id']}/jobs?per_page=100", paginate=True)
        report['failed_steps'] = [
            {'job': job['name'], 'step': step['name']}
            for page in pages for job in page['jobs'] for step in job.get('steps', [])
            if step.get('conclusion') in ('failure', 'timed_out', 'cancelled')]
    pages = api(f'repos/{repository}/issues?state=all&per_page=100', paginate=True)
    operation = synchronize(report, [i for page in pages for i in page], live=args.live)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'report': report, 'operation': operation, 'live': args.live}, indent=2) + '\n')
    summary = render(report) + f'\nIssue operation: {operation}; live updates: {args.live}\n'
    print(summary)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write(summary)


if __name__ == '__main__':
    main()
