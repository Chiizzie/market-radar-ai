import pytest
from market_radar_ai.market_data.providers.stocks import parse_directory

HEADER='Symbol|Security Name|Test Issue|ETF\n'
FOOTER='File Creation Time: 1102202621:00||||\n'


def test_filters_and_retains_explicit_exclusions():
    doc=parse_directory(HEADER+'MSFT|Microsoft|N|N\nTEST|Test|Y|N\nFUND|Fund|N|Y\nBRK.B|Berkshire|N|N\n'+FOOTER)
    assert [r['symbol'] for r in doc['listings']]==['MSFT']
    assert len(doc['excluded'])==3
    assert doc['listings'][0]['broker_eligibility']=='UNKNOWN'


@pytest.mark.parametrize('body',[
    HEADER+'MSFT|Microsoft|N|N\n',
    HEADER+'MSFT|Microsoft|N|N\nMSFT|Duplicate|N|N\n'+FOOTER,
    HEADER+'MSFT|Microsoft|?|N\n'+FOOTER,
    HEADER+'MSFT|Microsoft|N\n'+FOOTER,
])
def test_malformed_or_truncated_directory_rejected(body):
    with pytest.raises(ValueError): parse_directory(body)


def test_other_exchange_format():
    doc=parse_directory('ACT Symbol|Security Name|Test Issue|ETF|Exchange\nIBM|IBM|N|N|N\n'+FOOTER,other=True)
    assert doc['listings'][0]['listing_venue']=='N'
