"""Combine current native-currency candles and dated news for research only."""
from datetime import datetime
from hashlib import sha256
import json
from typing import Literal
from pydantic import AwareDatetime, Field, model_validator
from .paper_team import Frozen
from .news_input import NewsResearchInput, build_news_input
from ..market_data.models import Candle
from ..market_data.quality import validate_candles


class MarketEvidence(Frozen):
    symbol: str
    provider: str
    retrieved_at: AwareDatetime
    validated_at: AwareDatetime
    original_capture_sha256: str
    quote_currency: str = Field(pattern=r'^[A-Z]{3}$')
    candles: tuple[Candle, ...] = Field(min_length=2, max_length=60)

    @model_validator(mode='after')
    def check(self):
        if not 0 <= (self.validated_at-self.retrieved_at).total_seconds() <= 900:
            raise ValueError('Stale or future retrieval')
        if validate_candles(self.candles, now=self.validated_at,
                            max_age_seconds=900, expected_interval_seconds=300):
            raise ValueError('Unusable candles')
        if tuple(sorted(self.candles,key=lambda c:c.timestamp)) != self.candles:
            raise ValueError('Candles must be chronological')
        for row in self.candles:
            if (row.symbol != self.symbol or row.source != self.provider
                    or row.interval != '5m' or row.quote_currency != self.quote_currency
                    or (self.validated_at-row.timestamp).total_seconds() < 300
                    or not all(v.is_finite() for v in (row.open,row.high,row.low,row.close,row.volume))):
                raise ValueError('Candle identity, currency, interval or value mismatch')
        return self

    def source_id(self):
        return 'market:'+sha256(self.model_dump_json().encode()).hexdigest()


class CombinedResearchInput(Frozen):
    schema_version: Literal['combined-research-v1'] = 'combined-research-v1'
    symbol: str
    assembled_at: AwareDatetime
    news: NewsResearchInput
    market: MarketEvidence
    source_ids: tuple[str, ...]
    missing_data: tuple[str, ...] = (
        'broker_eligibility_unverified', 'eur_risk_and_trade_plan_not_supplied',
        'catalyst_significance_unverified', 'native_quotes_not_converted_to_eur')
    trade_authorized: Literal[False] = False

    @model_validator(mode='after')
    def check(self):
        if self.symbol != self.news.symbol or self.symbol != self.market.symbol:
            raise ValueError('Mixed symbols')
        if self.news.assembled_at != self.assembled_at or self.market.validated_at != self.assembled_at:
            raise ValueError('Packet clocks differ')
        if self.source_ids != (*self.news.source_ids, self.market.source_id()):
            raise ValueError('Citation IDs differ from supplied evidence')
        return self

    def digest(self):
        return sha256(self.model_dump_json().encode()).hexdigest()


def build_combined_input(document, feed, *, symbol, now):
    if document.get('format_version') != 2:
        raise ValueError('Capture version 2 required')
    matches=[c for c in document['captures'] if c.get('requested_symbol')==symbol and c.get('market')=='stocks']
    if len(matches)!=1:
        raise ValueError('Exactly one matching stock capture required')
    capture=matches[0]
    payload=capture['payload']
    checksum=sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    if checksum != capture['payload_sha256']:
        raise ValueError('Capture checksum mismatch')
    if (payload['provider_status']!='ok' or payload['quality_passed_at_capture'] is not True
            or payload['quality_issues'] or payload['research_only'] is not True
            or payload['disposition']!='NO_ACTION'):
        raise ValueError('Capture is not usable research evidence')
    candles=tuple(Candle.model_validate(row) for row in payload['candles'])
    if not candles:
        raise ValueError('Missing candles')
    market=MarketEvidence(symbol=symbol, provider=payload['provider'],
        retrieved_at=payload['retrieved_at'], validated_at=now, original_capture_sha256=checksum,
        quote_currency=candles[0].quote_currency,candles=candles)
    news=build_news_input(feed,symbol=symbol,now=now)
    return CombinedResearchInput(symbol=symbol,assembled_at=now,news=news,market=market,
        source_ids=(*news.source_ids,market.source_id()))


def main():
    import argparse
    from pathlib import Path
    from datetime import timezone
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--symbol',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        if any(p.stat().st_size>2_000_000 for p in (args.capture,args.evidence)):
            raise ValueError('Oversized input')
        packet=build_combined_input(json.loads(args.capture.read_text()),json.loads(args.evidence.read_text()),
            symbol=args.symbol,now=datetime.now(timezone.utc))
        result={'status':'ready_for_research','snapshot_id':packet.digest(),
                'input':packet.model_dump(mode='json'),'model_calls':0,'trade_authorized':False}
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        result={'status':'blocked','reason':'combined_evidence_unusable','input':None,
                'model_calls':0,'trade_authorized':False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='input'}))
    return int(result['status']=='blocked')


if __name__=='__main__':raise SystemExit(main())
