"""US listing discovery from Nasdaq Trader; never broker eligibility evidence."""
import csv
import io
import re
from datetime import datetime, timezone
import requests


def parse_directory(text, *, other=False):
    lines = text.strip().splitlines()
    if len(lines) < 3 or not lines[-1].startswith('File Creation Time:'):
        raise ValueError('Missing directory completion footer')
    reader = csv.DictReader(io.StringIO('\n'.join(lines[:-1])), delimiter='|')
    symbol_key = 'ACT Symbol' if other else 'Symbol'
    required = {symbol_key, 'Security Name', 'Test Issue', 'ETF'}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError('Unexpected directory schema')
    rows, excluded, seen = [], [], set()
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise ValueError('Malformed directory row')
        symbol = row[symbol_key].strip()
        if not symbol or symbol in seen:
            raise ValueError('Empty or duplicate listing identity')
        seen.add(symbol)
        if row['Test Issue'] not in ('Y','N') or row['ETF'] not in ('Y','N'):
            raise ValueError('Unknown directory flag')
        reason = ('test_issue' if row['Test Issue']=='Y' else
                  'etf_excluded' if row['ETF']=='Y' else
                  'symbol_mapping_required' if not re.fullmatch('[A-Z]{1,5}',symbol) else None)
        if reason:
            excluded.append({'symbol':symbol,'reason':reason})
            continue
        rows.append({'symbol':symbol,'name':row['Security Name'],
            'listing_venue':row.get('Exchange','NASDAQ'), 'broker_eligibility':'UNKNOWN',
            'provider_symbol_status':'CANDIDATE_REQUIRES_PRICE_VALIDATION'})
    if not seen:
        raise ValueError('Empty directory')
    return {'listings':rows,'excluded':excluded,'file_creation_marker':lines[-1].split('|')[0]}


class StockDirectory:
    BASE = 'https://www.nasdaqtrader.com/dynamic/SymDir/'

    def __init__(self, session=None):
        self.session = session or requests.Session()

    def discover(self):
        sources, failures = [], []
        for filename, other in [('nasdaqlisted.txt',False),('otherlisted.txt',True)]:
            try:
                with self.session.get(self.BASE+filename,timeout=(5,20),allow_redirects=False,stream=True) as response:
                    if response.status_code != 200:
                        raise ValueError('HTTP failure')
                    body = bytearray()
                    for chunk in response.iter_content(65536):
                        body.extend(chunk)
                        if len(body)>5_000_000:
                            raise ValueError('Directory size exceeds limit')
                parsed = parse_directory(body.decode('utf-8-sig'),other=other)
                sources.append({'url':self.BASE+filename,**parsed})
            except (requests.RequestException, ValueError, UnicodeError):
                failures.append({'source':filename,'code':'directory_fetch_or_validation_failed'})
        # Partial input must never silently replace a complete persistent universe.
        symbols = sorted({row['symbol'] for src in sources for row in src['listings']})
        return {'schema_version':1,'status':'ok' if not failures else 'error',
            'retrieved_at':datetime.now(timezone.utc).isoformat(),
            'coverage_scope':'US_EXCHANGE_DIRECTORY_NON_ETF_SIMPLE_SYMBOLS',
            'sources':sources,'failures':failures,'stocks':symbols if not failures else [],
            'broker_eligibility':'UNKNOWN'}


def main():
    import argparse
    import json
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=StockDirectory().discover()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'stocks':len(report['stocks']),'failures':report['failures']}))
    return int(report['status']!='ok')


if __name__=='__main__':
    raise SystemExit(main())
