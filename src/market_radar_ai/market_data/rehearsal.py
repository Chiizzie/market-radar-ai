"""Discovery-to-dashboard rehearsal. No AI calls, broker credentials or orders."""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .capture import capture_markets
from .queue import ScanQueue
from .providers.stocks import StockDirectory
from .providers.catalogues import KrakenCatalogue
from .providers.yahoo import YahooFinanceProvider
from .providers.kraken import KrakenProvider
from ..dashboard.export import build_snapshot
from ..dashboard.readiness import assess


def validated_universe(stocks, crypto, *, now):
    if now.tzinfo is None:
        raise ValueError('Aware clock required')
    if stocks['status'] != 'ok' or crypto.status != 'ok' or crypto.issues:
        raise ValueError('Discovery incomplete; existing queue preserved')
    retrieved = datetime.fromisoformat(stocks['retrieved_at'])
    for stamp in (retrieved, crypto.retrieved_at):
        if stamp.tzinfo is None or not 0 <= (now-stamp).total_seconds() <= 3600:
            raise ValueError('Discovery retrieval stale or invalid')
    sources = stocks['sources']
    if len(sources) != 2:
        raise ValueError('Both stock directories required')
    expected = {StockDirectory.BASE+'nasdaqlisted.txt', StockDirectory.BASE+'otherlisted.txt'}
    if {s['url'] for s in sources} != expected:
        raise ValueError('Unexpected directory sources')
    for source in sources:
        # Nasdaq specifies a timezone-less footer. Check its calendar date only;
        # do not invent a precise UTC creation time. Four days allows weekends.
        match = re.fullmatch(r'File Creation Time:\s*(\d{8})(\d{2}):?(\d{2})',source['file_creation_marker'])
        if not match:
            raise ValueError('Unrecognised directory creation marker')
        stamp = datetime.strptime(''.join(match.groups()),'%m%d%Y%H%M')
        age = (now.astimezone(timezone.utc).date()-stamp.date()).days
        if not 0 <= age <= 4:
            raise ValueError('Directory creation date stale or future')
    symbols = sorted({r['symbol'] for s in sources for r in s['listings']})
    if symbols != sorted(set(stocks['stocks'])) or not symbols:
        raise ValueError('Stock directory membership mismatch')
    pairs = sorted({i.symbol for i in crypto.instruments if i.active and i.quote_currency=='EUR'})
    if not pairs:
        raise ValueError('No active EUR crypto pairs')
    return {'stocks':symbols,'crypto':pairs}


def run(directory, *, stock_directory=None, crypto_catalogue=None, stock_fetch=None, crypto_fetch=None):
    directory = Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    def save(name, payload):
        (directory/name).write_text(json.dumps(payload,indent=2)+'\n')
    stocks = (stock_directory or StockDirectory()).discover()
    crypto = (crypto_catalogue or KrakenCatalogue()).discover_eur()
    save('stock-discovery.json', stocks)
    save('crypto-discovery.json', crypto.model_dump(mode='json'))
    now = datetime.now(timezone.utc)
    try:
        universe = validated_universe(stocks,crypto,now=now)
    except ValueError as exc:
        result={'pipeline_completed':False,'stage':'discovery','reason':str(exc),'trading_ready':False}
        save('rehearsal.json',result)
        return result
    save('universe.json',universe)
    queue = ScanQueue(directory/'scan-queue.sqlite3')
    for market, symbols in universe.items():
        queue.replace_universe(market,symbols)
    selection = queue.select(now=now,stocks=5,crypto=3)
    yahoo, kraken = YahooFinanceProvider(), KrakenProvider()
    capture = capture_markets(selection['stocks']['selected'],selection['crypto']['selected'],
        stock_fetch=stock_fetch or (lambda s:yahoo.fetch_history(s,period='1d',interval='5m')),
        crypto_fetch=crypto_fetch or kraken.fetch_ohlc)
    capture['queue_selection']=selection
    save('capture.json',capture)
    final_time=datetime.now(timezone.utc)
    snapshot=build_snapshot(capture,now=final_time)
    save('dashboard.json',snapshot)
    readiness=assess(capture,now=final_time)
    save('readiness.json',readiness)
    result={'pipeline_completed':True,'stage':'exported','trading_ready':False,
        'data_rehearsal_passed':readiness['data_rehearsal_passed'],
        'coverage':snapshot['coverage'],
        'stock_exclusions':sum(len(s['excluded']) for s in stocks['sources'])}
    save('rehearsal.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    result=run(args.output_dir)
    print(json.dumps(result,indent=2))
    return int(not result['pipeline_completed'])


if __name__=='__main__':
    raise SystemExit(main())
