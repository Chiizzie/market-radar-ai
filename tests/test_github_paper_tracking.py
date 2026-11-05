import base64,json
import pytest
from market_radar_ai.agents.github_paper_tracking import update,URL,BRANCH
from market_radar_ai.agents.paper_verdict import finalize
from test_paper_verdict import fixture,NOW

class Session:
    def __init__(self):self.state={'version':1,'decisions':[],'observations':[]};self.writes=0;self.fail=False
    def get(self,url,**kw):
        assert url==URL and kw['params']['ref']==BRANCH and not kw['allow_redirects']
        data={'encoding':'base64','size':len(json.dumps(self.state)),'sha':'version',
              'content':base64.b64encode(json.dumps(self.state).encode()).decode()}
        return type('Response',(),{'status_code':200,'json':lambda _:data})()
    def put(self,url,**kw):
        assert url==URL and kw['json']['sha']=='version'
        self.writes+=1
        if not self.fail:self.state=json.loads(base64.b64decode(kw['json']['content']))
        return type('Response',(),{'status_code':409 if self.fail else 200})()


def test_durable_reconstruction_and_noop_does_not_commit(monkeypatch):
    _,packet,audit,_=fixture(monkeypatch);decision=finalize(packet,audit,{},None,now=NOW)
    session=Session()
    r=update('fake',now=NOW,decision=decision,session=session)
    assert r['trades'][0]['state']=='watching' and session.writes==1
    assert update('fake',now=NOW,session=session)==r and session.writes==1


def test_conflict_fails_without_silent_reset(monkeypatch):
    _,packet,audit,_=fixture(monkeypatch);decision=finalize(packet,audit,{},None,now=NOW)
    session=Session();session.fail=True
    with pytest.raises(RuntimeError,match='write_unconfirmed'):update('fake',now=NOW,decision=decision,session=session)
    assert session.state['decisions']==[]
