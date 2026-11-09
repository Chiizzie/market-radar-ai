"""Prospective competitor-strength breakout experiment; no AI, alerts or orders."""
from datetime import timedelta
from decimal import Decimal as D
from zoneinfo import ZoneInfo
from .candidate_packages import digest
from .method_scenarios import scenario as common_scenario
from .paper_comparison import aware
from ..market_data.models import Candle
from ..market_data.catalyst_links import RELATIONSHIPS, RELATIONSHIP_SOURCE, response, headline_mentions_source

STRATEGY='competitor_strength_breakout_shadow_v1'
PROTOCOL={'version':'competitor-strength-shadow-v1','rules':{
    'strategy_id':STRATEGY,'map':'NVDA_AMD_INTC_2026_annual_report','headline_must_name_source':True,
    'maximum_news_age_seconds':86400,'maximum_news_retrieval_age_seconds':900,
    'maximum_snapshot_age_seconds':180,'post_news_window_seconds':[60,1800],
    'maximum_window_alignment_seconds':60,'minimum_target_gain_pct':'.25',
    'minimum_outperformance_pp':'.5','minimum_day_turnover_usd':10000000,
    'maximum_completed_bar_age_seconds':360,'minimum_bars':6,'range_bars':3,'minimum_range_turnover_usd':1000000,
    'maximum_range_pct':5,'entry_buffer_bps':10,'above_six_bar_hlc3_vwap':True,
    'target':'net_2R_capped_at_projected_three_range_extension'},
    'fill_clock':'local_receipt_after_durable_enrolment',
    'news':'indirect_competitor_hypothesis_not_directional_headline_classification',
    'eligibility':'unique_US_Invest_catalogue_candidate_not_account_permission',
    'assumed_round_trip_bps':40,'maximum_planned_loss_eur':20,'independent_allocation_eur':500,
    'entry_expiry_seconds':60,'maximum_spread_and_entry_gap_bps':20,
    'capacity':40,'currency':'EUR','no_ai':True,'no_alerts':True}
PROTOCOL_ID=digest(PROTOCOL)


def measure(candles,daily,*,symbol,now):
    now=aware(now);features={};blocked=[]
    try:
        rows=[Candle.model_validate(r) for r in candles][-6:]
        local=now.astimezone(ZoneInfo('America/New_York'))
        if len(rows)!=6 or local.weekday()>=5:
            raise ValueError('history')
        for index,row in enumerate(rows):
            if (row.symbol!=symbol or row.source!='alpaca_iex' or row.quote_currency!='USD'
                or row.interval!='5m' or row.volume<=0
                or row.timestamp.astimezone(ZoneInfo('America/New_York')).date()!=local.date()
                or row.timestamp.astimezone(ZoneInfo('America/New_York')).time().replace(tzinfo=None)<local.replace(hour=9,minute=30,second=0,microsecond=0).time().replace(tzinfo=None)
                or (index and row.timestamp-rows[index-1].timestamp!=timedelta(minutes=5))):
                raise ValueError('bars')
        if not 0<=(now-(rows[-1].timestamp+timedelta(minutes=5))).total_seconds()<=360:
            raise ValueError('incomplete_or_stale')
        high=max(r.high for r in rows[-3:]);low=min(r.low for r in rows[-3:]);width=high-low
        vwap=sum((r.high+r.low+r.close)/3*r.volume for r in rows)/sum(r.volume for r in rows)
        turnover=sum(r.close*r.volume for r in rows[-3:]);entry=high*D('1.001')
        if width<=0 or width/low*100>5:blocked.append('competitor_range_width_invalid')
        if turnover<1000000:blocked.append('competitor_recent_turnover_below_one_million_usd')
        if rows[-1].close<=vwap or rows[-1].close<=rows[-3].open:blocked.append('competitor_chart_strength_unconfirmed')
        features={'entry_native':str(entry),'stop_native':str(low),'target_cap_native':str(entry+3*width),
            'range_high_native':str(high),'range_low_native':str(low),'observed_turnover_usd':str(turnover),
            'target_cap_basis':'projected_three_range_extension_not_observed_resistance'}
    except (ValueError,TypeError,KeyError,ArithmeticError):blocked.append('competitor_bars_invalid_or_stale')
    return {'blockers':blocked,'features':features}


def scenario(inputs,*,now):
    now=aware(now)
    def measurement(candles,daily,*,symbol,now):
        result=measure(candles,daily,symbol=symbol,now=now)
        supported=[]
        try:
            evidence=inputs['competitor_evidence'];snapshots=evidence['snapshots']
            if len(evidence['links'])>40:raise ValueError('capacity')
            for link in evidence['links']:
                source=link['source_symbol'];published=aware(link['published_at']);received=aware(link['news_retrieved_at'])
                if (not headline_mentions_source(link.get('headline'),source) or symbol not in RELATIONSHIPS.get(source,()) or link['symbol']!=symbol
                    or link['relationship_source']!=RELATIONSHIP_SOURCE or link['direct_target_news'] is not False
                    or not link['evidence_id'] or not link['news_url'].startswith('https://')
                    or not 0<=(now-published).total_seconds()<=86400
                    or not published<=received<=now or (now-received).total_seconds()>900):continue
                observed=response(snapshots.get(source,{}),snapshots.get(symbol,{}),published=published,now=now)
                if observed['state']=='relative_strength_observed':
                    supported.append({'source_symbol':source,'evidence_id':link['evidence_id'],
                        'news_url':link['news_url'],'published_at':link['published_at'],'response':observed})
        except (ValueError,TypeError,KeyError,AttributeError,ArithmeticError):
            result['blockers'].append('competitor_evidence_invalid_or_missing')
        if not supported:result['blockers'].append('post_news_competitor_strength_unconfirmed')
        result['features']['indirect_catalysts']=supported
        return result
    return common_scenario(inputs,now=now,measurement_fn=measurement,protocol=PROTOCOL)
