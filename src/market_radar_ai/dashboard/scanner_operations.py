"""Read-only GitHub run health and verified backup-upload receipts. No model access."""
import argparse
import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

import requests
from ..agents.candidate_packages import digest
from ..agents.comparison_live import EventClient, envelope

REPO='Chiizzie/market-radar-ai'
PROTOCOL={'version':'scanner-operations-v1','repository':REPO,'monitoring_since':'2026-11-07',
          'expected_window':'weekdays_08:00_to_23:00_Europe/Dublin','stale_after_minutes':20}
EXPERIMENT=digest(PROTOCOL)
JOBS={'collect','review','paper-watcher','method-shadow','account-sync','market-context'}
STATES={'queued','in_progress','completed','waiting','pending','requested'}
CONCLUSIONS={'success','failure','neutral','cancelled','skipped','timed_out','action_required','stale','startup_failure'}


def at(value):
    d=datetime.fromisoformat(value.replace('Z','+00:00'))
    if d.tzinfo is None: raise ValueError('aware_operation_time_required')
    return d.isoformat()


class GitHubRead:
    def __init__(self,token,session=None):
        if not token: raise ValueError('github_read_not_configured')
        self.token=token;self.session=session or requests.Session()
    def get(self,path):
        if not re.fullmatch(r'/actions/(workflows/scheduled-scanner\.yml/runs\?branch=main&per_page=20|runs/\d+/jobs\?per_page=100|artifacts/\d+)',path):
            raise ValueError('unsupported_health_path')
        with self.session.get('https://api.github.com/repos/'+REPO+path,
            headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json'},
            timeout=(5,12),allow_redirects=False,stream=True) as response:
            if response.status_code!=200: raise ValueError('github_health_unavailable')
            raw=bytearray()
            for part in response.iter_content(65536):
                raw.extend(part)
                if len(raw)>2_000_000: raise ValueError('health_response_capacity')
        return json.loads(raw)


def run_row(r):
    if (type(r['id']) is not int or r['id']<=0 or r['head_branch']!='main'
            or r['name']!='Scheduled research collection' or r['status'] not in STATES
            or r['conclusion'] not in CONCLUSIONS|{None}): raise ValueError('invalid_run_metadata')
    return {'run_id':r['id'],'status':r['status'],'conclusion':r['conclusion'],
        'created_at':at(r['created_at']),'started_at':at(r['run_started_at']) if r.get('run_started_at') else None,
        'updated_at':at(r['updated_at']),'url':f'https://github.com/{REPO}/actions/runs/{r["id"]}'}


def health(github, *, now, include_experiments=False, current=False):
    result={'schema_version':'scanner-operations-v1','protocol_id':EXPERIMENT,'as_of':now.isoformat(),
        'evaluation_day':now.date().isoformat(),'dataset_kind':'forward','trade_authorized':False,
        'monitoring_since':PROTOCOL['monitoring_since'],'model_calls':0,'source_status':'unavailable',
        'runs':[],'jobs':[],'jobs_run_id':None,'jobs_complete':False,'errors':[]}
    try:
        data=github.get('/actions/workflows/scheduled-scanner.yml/runs?branch=main&per_page=20')
        if not isinstance(data['workflow_runs'],list) or len(data['workflow_runs'])>20:raise ValueError('run_capacity')
        rows=[run_row(r) for r in data['workflow_runs']]
        rows.sort(key=lambda r:(r['created_at'],r['run_id']),reverse=True)
        result.update(source_status='received',runs=rows)
        # The stored operations-v1 view keeps its original completed-run schema.
        # Readiness can inspect current jobs directly, including independent
        # observers, instead of turning a previous success into a current pass.
        latest=(rows[0] if rows else None) if current else next((r for r in rows if r['status']=='completed'),None)
        if latest:
            data=github.get(f'/actions/runs/{latest["run_id"]}/jobs?per_page=100')
            if data['total_count']!=len(data['jobs']) or len(data['jobs'])>100: raise ValueError('job_pagination_incomplete')
            jobs=[]
            for j in data['jobs']:
                allowed=JOBS|{'comparison-watcher','strategy-experiment','entry-confirmation','entry-enrol'} if include_experiments else JOBS
                if j['name'] not in allowed: continue
                if j['status'] not in STATES or j['conclusion'] not in CONCLUSIONS|{None}: raise ValueError('invalid_job')
                jobs.append({'name':j['name'],'status':j['status'],'conclusion':j['conclusion'],
                    'started_at':at(j['started_at']) if j.get('started_at') else None,
                    'completed_at':at(j['completed_at']) if j.get('completed_at') else None})
            result.update(jobs=jobs,jobs_run_id=latest['run_id'],jobs_complete=True)
    except (requests.RequestException,ValueError,KeyError,TypeError,AttributeError):
        result['errors'].append('github_run_or_job_evidence_unavailable')
    return result


def backup_receipt(github, *, artifact_id, manifest, family, now):
    if family not in ('comparison','method') or type(artifact_id) is not int or artifact_id<=0:
        raise ValueError('invalid_backup_identity')
    data=github.get(f'/actions/artifacts/{artifact_id}')
    run=data['workflow_run']['id']
    if (data['id']!=artifact_id or data['name']!=f'{family}-recovery-{run}' or data['expired'] is not False
            or data['workflow_run']['head_branch']!='main' or type(data['size_in_bytes']) is not int
            or data['size_in_bytes']<=0 or datetime.fromisoformat(at(data['expires_at']))<=now
            or manifest['dataset_kind']!='forward' or not re.fullmatch(r'[a-f0-9]{64}',manifest['sha256_uncompressed'])
            or type(manifest['event_count']) is not int or manifest['event_count']<1
            or manifest['day']!=now.date().isoformat()): raise ValueError('unverified_backup_upload')
    return {'schema_version':'scanner-backup-receipt-v1','protocol_id':EXPERIMENT,'as_of':now.isoformat(),
        'evaluation_day':now.date().isoformat(),'dataset_kind':'forward','trade_authorized':False,
        'family':family,'backup_day':manifest['day'],'artifact_id':artifact_id,'run_id':run,
        'created_at':at(data['created_at']),'expires_at':at(data['expires_at']),
        'url':f'https://github.com/{REPO}/actions/runs/{run}/artifacts/{artifact_id}',
        'sha256_uncompressed':manifest['sha256_uncompressed'],'event_count':manifest['event_count'],
        'upload_confirmed':True,'restore_of_this_archive_tested':False,'model_calls':0}


def deferred_health_publication(report, run_id, capture_dir, now):
    """Space secondary writes only after a proven primary read timeout."""
    if not run_id or not capture_dir or str(report.get('jobs_run_id')) != run_id:
        return None
    if not report.get('jobs_complete') or not any(
        job['name'] == 'collect' and job['conclusion'] == 'failure' for job in report['jobs']
    ):
        return None
    runs = report['runs']
    parent = next((row for row in runs if str(row['run_id']) == run_id), None)
    if not parent or parent['conclusion'] != 'failure':
        return None
    dispatched = datetime.fromisoformat(at(parent['created_at'])).astimezone(UTC)
    quarter = dispatched.replace(minute=dispatched.minute // 15 * 15, second=0, microsecond=0)
    if not 0 <= (now - dispatched).total_seconds() < 1200:
        return None
    # A missing or delayed dispatch must never eliminate the first reporting
    # opportunity of a quarter. Use the real GitHub history, not a cron slot.
    if not any(row['conclusion'] in ('success', 'failure') and
               quarter <= datetime.fromisoformat(at(row['created_at'])) < dispatched for row in runs):
        return None
    try:
        directory = Path(capture_dir)
        with (directory / 'delivery.json').open('rb') as source:
            raw_receipt = source.read(8193)
        if len(raw_receipt) > 8192:
            return None
        receipt = json.loads(raw_receipt)
        if (not isinstance(receipt, dict) or receipt.get('state') != 'scanner_snapshot_delivery_unconfirmed'
                or receipt.get('reason') != 'read_timeout' or receipt.get('trade_authorized') is not False):
            return None
        generated = datetime.fromisoformat(at(receipt['generated_at_dublin']))
        if not dispatched <= generated <= now:
            return None
        with (directory / 'dashboard.json').open('rb') as captured:
            fingerprint = hashlib.file_digest(captured, 'sha256').hexdigest()
        if fingerprint != receipt.get('snapshot_id'):
            return None
    except (OSError, TypeError, ValueError, KeyError, AttributeError):
        return None
    return {'state': 'health_publication_deferred', 'reason': 'primary_dashboard_read_timeout',
            'run_id': parent['run_id'], 'snapshot_id': fingerprint, 'as_of': now.isoformat(),
            'report_archived_locally': True, 'model_calls': 0, 'trade_authorized': False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=Path('artifacts/scanner-health/report.json'))
    p.add_argument('--artifact-id',type=int);p.add_argument('--family',choices=['comparison','method'])
    p.add_argument('--manifest',type=Path)
    args=p.parse_args(); now=datetime.now(UTC)
    github=GitHubRead(os.environ.get('GH_HEALTH_TOKEN'))
    if args.artifact_id:
        if not args.family or not args.manifest: p.error('family and manifest required for a backup receipt')
        report=backup_receipt(github,artifact_id=args.artifact_id,manifest=json.loads(args.manifest.read_text()),family=args.family,now=now)
        kind='backup_report'
    else:report=health(github,now=now);kind='ops_report'
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    if kind == 'ops_report':
        deferred = deferred_health_publication(report, os.getenv('HEALTH_TIMEOUT_RUN_ID'),
                                               os.getenv('HEALTH_CAPTURE_DIR'), now)
        if deferred:
            args.output.with_name('publication.json').write_text(json.dumps(deferred, indent=2) + '\n')
            print(json.dumps(deferred))
            raise SystemExit('Health report saved. Dashboard publication deferred after confirmed primary timeout.')
    # Every run archives its full health report. A timed-out write can still
    # hold the partition lock when an immediate retry reaches the database.
    client = EventClient(os.environ.get('REVIEW_INGEST_SECRET'), retry_appends=kind != 'ops_report')
    client.append(EXPERIMENT,[envelope(kind,report,now)])
    print(json.dumps({'state':kind+'_recorded','source_status':report.get('source_status','upload_confirmed'),
                      'model_calls':0,'trade_authorized':False}))


if __name__=='__main__': main()
