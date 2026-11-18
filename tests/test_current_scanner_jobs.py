from datetime import UTC, datetime, timedelta
from test_execution_readiness import GitHub, result, states


class Current(GitHub):
    def __init__(self, failure='comparison-watcher'):
        super().__init__(datetime(2026,11,13,15,tzinfo=UTC));self.failure=failure
    def get(self,path):
        if 'workflows' in path:
            old=super().get(path)['workflow_runs'][0]
            new={**old,'id':124,'created_at':(self.now+timedelta(minutes=1)).isoformat(),
                 'status':'in_progress','conclusion':None}
            return {'workflow_runs':[new,old]}
        if '/124/' not in path:raise AssertionError('readiness must inspect current run')
        jobs=super().get(path)['jobs']
        for name in ('comparison-watcher','strategy-experiment','entry-confirmation','entry-enrol'):
            jobs.append({**jobs[0],'name':name,'conclusion':'failure' if name==self.failure else 'success'})
        return {'total_count':len(jobs),'jobs':jobs}


def test_current_comparison_failure_overrides_previous_completed_success():
    r=result(github=Current())
    assert states(r)['scanner_jobs']=='blocked'


def test_experimental_failure_is_visible_even_if_ordinary_jobs_pass():
    assert states(result(github=Current('entry-confirmation')))['scanner_jobs']=='blocked'


def test_missing_required_observer_cannot_pass_readiness():
    assert states(result(github=GitHub()))['scanner_jobs']=='pending'
