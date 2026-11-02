"""Persistent fair scheduling of candle checks; no trade or eligibility decisions."""
import sqlite3
from datetime import datetime


class ScanQueue:
    def __init__(self, path):
        self.path = str(path)
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS scan_queue (market TEXT, symbol TEXT, last_selected REAL, PRIMARY KEY(market,symbol))')

    def replace_universe(self, market, symbols):
        if market not in ('stocks', 'crypto'):
            raise ValueError('Unknown market')
        symbols = sorted(set(s.strip().upper() for s in symbols if s.strip()))
        if len(symbols) > 50000:
            raise ValueError('Universe exceeds supported bound')
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TEMP TABLE incoming (symbol TEXT PRIMARY KEY)')
            db.executemany('INSERT INTO incoming VALUES (?)', [(s,) for s in symbols])
            db.execute('DELETE FROM scan_queue WHERE market=? AND symbol NOT IN (SELECT symbol FROM incoming)', (market,))
            db.execute('INSERT OR IGNORE INTO scan_queue(market,symbol) SELECT ?,symbol FROM incoming', (market,))

    def select(self, *, now: datetime, stocks=20, crypto=5):
        if now.tzinfo is None or any(type(n) is not int or not 0 <= n <= 500 for n in (stocks, crypto)):
            raise ValueError('Aware clock and quotas 0..500 required')
        output = {}
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute('BEGIN IMMEDIATE')
            for market, quota in (('stocks', stocks), ('crypto', crypto)):
                total = db.execute('SELECT COUNT(*) FROM scan_queue WHERE market=?', (market,)).fetchone()[0]
                rows = db.execute('SELECT symbol FROM scan_queue WHERE market=? ORDER BY last_selected IS NOT NULL,last_selected,symbol LIMIT ?', (market, quota)).fetchall()
                symbols = [r[0] for r in rows]
                previous = db.execute('SELECT MAX(last_selected) FROM scan_queue WHERE market=?', (market,)).fetchone()[0]
                stamp = max(now.timestamp(), (previous + 0.000001) if previous is not None else now.timestamp())
                db.executemany('UPDATE scan_queue SET last_selected=? WHERE market=? AND symbol=?', [(stamp,market,s) for s in symbols])
                output[market] = {'selected': symbols, 'universe_count': total, 'deferred_count': total-len(symbols)}
        return output
