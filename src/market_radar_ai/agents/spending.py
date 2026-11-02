"""Persistent atomic reservations, in integer micro-EUR. No paid API integration."""
import sqlite3
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo


class SpendingLedger:
    def __init__(self, path, daily_limit_microeur, *, monthly_limit_microeur=None,
                 lifetime_limit_microeur=None):
        if type(daily_limit_microeur) is not int or daily_limit_microeur < 0:
            raise ValueError('Limit must be a nonnegative integer')
        for limit in (monthly_limit_microeur, lifetime_limit_microeur):
            if limit is not None and (type(limit) is not int or limit < 0):
                raise ValueError('Limit must be a nonnegative integer')
        self.monthly_limit = monthly_limit_microeur
        self.lifetime_limit = lifetime_limit_microeur
        self.path, self.limit = str(path), daily_limit_microeur
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS spend (id TEXT PRIMARY KEY, day TEXT NOT NULL, reserved INTEGER NOT NULL, actual INTEGER)')

    def reserve(self, request_id, maximum_microeur, now: datetime):
        if not request_id or now.tzinfo is None or type(maximum_microeur) is not int or maximum_microeur <= 0:
            raise ValueError('Invalid reservation')
        day = now.astimezone(ZoneInfo('Europe/Dublin')).date().isoformat()
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM spend WHERE id=?', (request_id,)).fetchone():
                raise ValueError('Request ID already reserved; do not repeat a paid call')
            total = db.execute('SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM spend WHERE day=?',(day,)).fetchone()[0]
            if total + maximum_microeur > self.limit:
                raise RuntimeError('daily_spending_limit')
            for label, limit, condition, parameters in (
                ('monthly', self.monthly_limit, 'WHERE substr(day,1,7)=?', (day[:7],)),
                ('lifetime', self.lifetime_limit, '', ()),
            ):
                if limit is not None:
                    used = db.execute(
                        'SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM spend '
                        + condition, parameters).fetchone()[0]
                    if used + maximum_microeur > limit:
                        raise RuntimeError(f'{label}_spending_limit')
            db.execute('INSERT INTO spend VALUES(?,?,?,NULL)',(request_id,day,maximum_microeur))

    def settle(self, request_id, actual_microeur):
        if type(actual_microeur) is not int or actual_microeur < 0:
            raise ValueError('Invalid actual cost')
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT reserved,actual FROM spend WHERE id=?',(request_id,)).fetchone()
            if row is None: raise KeyError(request_id)
            if row[1] is not None:
                if row[1] != actual_microeur: raise ValueError('Conflicting settlement')
                return
            # Preserve the real charge even if an adapter underestimated its bound.
            db.execute('UPDATE spend SET actual=? WHERE id=?',(actual_microeur,request_id))
        if actual_microeur > row[0]:
            raise RuntimeError('reservation_exceeded_actual_charge_recorded')
