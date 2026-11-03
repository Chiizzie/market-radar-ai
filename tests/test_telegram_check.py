import pytest
from market_radar_ai.dashboard.telegram_check import execute,TEXT
ENV=dict(GITHUB_REPOSITORY='Chiizzie/market-radar-ai',GITHUB_REF='refs/heads/phase-1/market-data-layer',GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_RUN_ATTEMPT='1',SEND_TELEGRAM_TEST='true',TELEGRAM_BOT_TOKEN='test-secret',TELEGRAM_CHAT_ID='123')

def test_manual_test_is_fixed_and_confirms_destination():
    class Session:
        def post(self,url,**kw):
            assert kw['json']['text']==TEXT and kw['allow_redirects'] is False
            return type('R',(),{'status_code':200,'json':lambda self:{'ok':True,'result':{'chat':{'id':123},'message_id':1}}})()
    assert execute(ENV,session=Session())['state']=='test_delivery_confirmed'

@pytest.mark.parametrize('change',[dict(GITHUB_RUN_ATTEMPT='2'),dict(SEND_TELEGRAM_TEST='false'),dict(GITHUB_EVENT_NAME='push'),dict(GITHUB_REPOSITORY='Chiizzie/market-radar')])
def test_unauthorized_execution_stops(change):
    with pytest.raises(ValueError):execute(dict(ENV,**change))

def test_timeout_is_redacted_and_not_retried():
    class Session:
        count=0
        def post(self,*args,**kwargs):
            self.count+=1;raise RuntimeError('test-secret')
    session=Session()
    with pytest.raises(RuntimeError) as e:execute(ENV,session=session)
    assert session.count==1 and 'test-secret' not in str(e.value)
