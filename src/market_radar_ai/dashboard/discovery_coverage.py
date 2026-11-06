"""Aggregate discovery stages, distinct from the selected-symbol capture contract."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Counts(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    catalogue: int = Field(ge=0,le=20000)
    candidates: int = Field(ge=0,le=20200)
    unmapped: int = Field(ge=0,le=20000)
    excluded: int = Field(ge=0,le=20000)
    quote_requested: int = Field(ge=0,le=20200)
    quote_usable: int = Field(ge=0,le=20200)
    quote_unavailable: int = Field(ge=0,le=20200)
    technical_checked: int = Field(ge=0,le=300)
    technical_usable: int = Field(ge=0,le=300)
    technical_unavailable: int = Field(ge=0,le=300)
    technical_deferred: int = Field(ge=0,le=20200)
    detail_selected: int = Field(ge=0,le=40)
    detail_from_pool: int = Field(ge=0,le=40)
    detail_deferred: int = Field(ge=0,le=20200)
    fallback: bool

    @model_validator(mode='after')
    def reconcile(self):
        if (self.quote_requested!=self.quote_usable+self.quote_unavailable
                or self.quote_requested>self.candidates
                or self.technical_checked!=self.technical_usable+self.technical_unavailable
                or self.candidates!=self.technical_checked+self.technical_deferred
                or self.candidates!=self.detail_from_pool+self.detail_deferred
                or self.detail_from_pool>self.detail_selected):
            raise ValueError('discovery_counts_inconsistent')
        return self


class Coverage(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    schema_version: Literal['discovery-coverage-v1']
    observed_at: str
    stocks: Counts | None
    crypto: Counts | None
    model_calls: Literal[0]
    trade_authorized: Literal[False]


def validate(value, *, now, document):
    parsed=Coverage.model_validate(value)
    at=datetime.fromisoformat(parsed.observed_at)
    if at.tzinfo is None or at>now:raise ValueError('invalid_discovery_clock')
    for market in ('stocks','crypto'):
        counts=getattr(parsed,market)
        if counts and counts.detail_selected!=sum(c['market']==market for c in document['captures']):
            raise ValueError('discovery_capture_selection_mismatch')
    if parsed.crypto and (parsed.crypto.detail_selected>30 or parsed.crypto.catalogue>500
            or parsed.crypto.catalogue!=parsed.crypto.candidates+parsed.crypto.excluded+parsed.crypto.unmapped):
        raise ValueError('crypto_discovery_identity_counts')
    return parsed.model_dump()


def build_coverage(stocks, crypto, document, *, now):
    out={'schema_version':'discovery-coverage-v1','observed_at':now.isoformat(),
         'stocks':None,'crypto':None,'model_calls':0,'trade_authorized':False}
    if stocks and 'coverage' in stocks:
        c=stocks['coverage'];q=stocks.get('snapshot_coverage') or {}
        out['stocks']=dict(catalogue=c['catalogue_candidates'],candidates=c['candidate_pool'],
            unmapped=0,excluded=0,quote_requested=q.get('requested',0),quote_usable=q.get('fresh',0),
            quote_unavailable=q.get('unavailable_or_stale',0),
            technical_checked=c['technical_checked'],technical_usable=c['technical_usable'],
            technical_unavailable=c['technical_unavailable'],technical_deferred=c['technical_deferred'],
            detail_selected=sum(r['market']=='stocks' for r in document['captures']),
            detail_from_pool=c['research_selected'],detail_deferred=c['research_deferred'],fallback=stocks['fallback_used'])
    if crypto:
        from ..market_data.crypto_identities import ASSETS, STABLE_ASSETS
        assets=(crypto.get('catalogue') or {}).get('payload',{}).get('assets',[])
        allowed={(a['symbol'],a['name']) for a in assets}
        pool={p for p,a in ASSETS.items() if a in allowed and a[0] not in STABLE_ASSETS}
        rows=[r for r in document['captures'] if r['market']=='crypto']
        checked=[r for r in rows if r['requested_symbol'] in pool]
        usable=sum(r['payload']['quality_passed_at_capture'] for r in checked)
        c=crypto['coverage']
        out['crypto']=dict(catalogue=c['catalogue_candidates'],candidates=c['candidate_pool'],
            unmapped=c['unmapped'],excluded=c['excluded_stable_assets'],quote_requested=c['quote_checked'],
            quote_usable=c['quote_usable'],quote_unavailable=c['quote_unavailable'],
            technical_checked=len(checked),technical_usable=usable,technical_unavailable=len(checked)-usable,
            technical_deferred=len(pool)-len(checked),detail_selected=len(rows),detail_from_pool=len(checked),
            detail_deferred=len(pool)-len(checked),fallback=not bool(crypto['selected_pairs']))
    return validate(out,now=now,document=document)
