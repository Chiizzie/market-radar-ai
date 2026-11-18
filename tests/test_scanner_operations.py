from datetime import datetime,UTC,timedelta
from types import SimpleNamespace
import pytest
from market_radar_ai.dashboard.scanner_operations import health,backup_receipt,GitHubRead

NOW=datetime(2026,11,9,22,20,tzinfo=UTC)


def test_failed_and_skipped_jobs_remain_distinct_and_private_fields_are_dropped():
    run={'id':7,'name':'Scheduled research collection','head_branch':'main','created_at':NOW.isoformat(),
        'run_started_at':NOW.isoformat(),'updated_at':NOW.isoformat(),'status':'completed','conclusion':'failure',
        'secret_extra':'never export'}
    jobs=[{'name':name,'status':'completed','conclusion':state,'started_at':NOW.isoformat(),'completed_at':NOW.isoformat(),
           'private_output':'never export'} for name,state in [('collect','failure'),('review','skipped')]]
    github=SimpleNamespace(get=lambda path:{'workflow_runs':[run]} if 'workflows/' in path else {'total_count':2,'jobs':jobs})
    r=health(github,now=NOW)
    assert r['runs'][0]['conclusion']=='failure' and r['jobs'][1]['conclusion']=='skipped'
    assert r['jobs_complete'] and 'never export' not in str(r)
    assert not r['trade_authorized'] and r['model_calls']==0


def test_unavailable_or_truncated_jobs_are_not_success():
    github=SimpleNamespace(get=lambda path:(_ for _ in ()).throw(ValueError('secret body')))
    r=health(github,now=NOW)
    assert r['source_status']=='unavailable' and not r['jobs_complete'] and r['runs']==[]
    assert 'secret body' not in str(r)
    with pytest.raises(ValueError):GitHubRead('test').get('/user')


def test_backup_receipt_requires_actual_nonexpired_matching_upload():
    data={'id':9,'workflow_run':{'id':7,'head_branch':'main'},'name':'comparison-recovery-7',
        'expired':False,'size_in_bytes':1000,'created_at':NOW.isoformat(),'expires_at':(NOW+timedelta(days=30)).isoformat()}
    manifest={'dataset_kind':'forward','sha256_uncompressed':'a'*64,'event_count':1,'day':'2026-11-09'}
    github=SimpleNamespace(get=lambda path:data)
    r=backup_receipt(github,artifact_id=9,manifest=manifest,family='comparison',now=NOW)
    assert r['upload_confirmed'] and not r['restore_of_this_archive_tested']
    data['expired']=True
    with pytest.raises(ValueError):backup_receipt(github,artifact_id=9,manifest=manifest,family='comparison',now=NOW)
