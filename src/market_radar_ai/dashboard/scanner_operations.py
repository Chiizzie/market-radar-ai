"""Read-only GitHub run health and verified backup-upload receipts. No model access."""
import argparse
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
JOBS={'collect','review','paper-watcher','method-shadow','account-sync'}
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


def health(github, *, now):
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
        latest=next((r for r in rows if r['status']=='completed'),None)
        if latest:
            data=github.get(f'/actions/runs/{latest["run_id"]}/jobs?per_page=100')
            if data['total_count']!=len(data['jobs']) or len(data['jobs'])>100: raise ValueError('job_pagination_incomplete')
            jobs=[]
            for j in data['jobs']:
                if j['name'] not in JOBS: continue
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
    EventClient(os.environ.get('REVIEW_INGEST_SECRET')).append(EXPERIMENT,[envelope(kind,report,now)])
    print(json.dumps({'state':kind+'_recorded','source_status':report.get('source_status','upload_confirmed'),
                      'model_calls':0,'trade_authorized':False}))


if __name__=='__main__': main()
