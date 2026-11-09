"""Bounded curated coverage; these groups are research routing, not index membership."""
from decimal import Decimal

CORE = ('NVDA','AMD','AVGO','MU','MSFT','AAPL','AMZN','GOOGL','META','TSLA','PLTR','CRM')
GROUPS = {
    'semiconductors': ('NVDA','AMD','AVGO','MU','ARM','TSM','INTC','QCOM'),
    'software': ('MSFT','CRM','PLTR','ORCL','ADBE','CRWD','PANW','SNOW'),
    'internet': ('AMZN','GOOGL','META','NFLX','UBER','SHOP'),
    'consumer': ('TSLA','WMT','COST','HD','NKE','MCD'),
    'financials': ('JPM','BAC','GS','MS','V','MA'),
    'healthcare': ('LLY','UNH','JNJ','ABBV','MRK','PFE'),
    'energy': ('XOM','CVX','COP','SLB','OXY'),
    'industrials': ('CAT','GE','GEV','BA','DE','RTX'),
}


def leaders(evidence):
    """One positive, fresh, >=USD10m observed-turnover name per curated group."""
    out=[]
    for members in GROUPS.values():
        eligible=[]
        for s in members:
            r=evidence.get(s,{})
            try:
                change=Decimal(str(r.get('day_change_pct',0)))
                turnover=Decimal(str(r.get('turnover_usd',0)))
                if r.get('snapshot_status')=='fresh' and change.is_finite() and turnover.is_finite() and change>0 and turnover>=10_000_000:
                    eligible.append((change,turnover,s))
            except (ValueError,ArithmeticError): pass
        if eligible:out.append(max(eligible)[2])
    return list(dict.fromkeys(out))


def reserve_screen(ordered, pool, sector, limit):
    members=set(pool)
    return list(dict.fromkeys([s for s in (*CORE,*sector) if s in members]+ordered))[:limit]


def select_details(candidates, sector, now, limit):
    from .discovery import select
    usable=set(candidates); chosen=[]; lanes={}
    def add(symbols, lane, cap):
        added=0
        for s in symbols:
            if s in usable and s not in lanes and added<cap and len(chosen)<limit:
                chosen.append(s);lanes[s]=lane;added+=1
    add(CORE,'liquid_core',12)
    add(sector,'sector_mover',8)
    add(candidates,'technical_leader',10)
    rest=[s for s in candidates if s not in lanes]
    # Rotation gets at least nine of the normal 39 slots with all lanes full.
    if rest:
        slots=limit-len(chosen);offset=(int(now.timestamp())//300*max(1,slots))%len(rest)
        add(rest[offset:]+rest[:offset],'rotation',slots)
    return chosen,lanes
