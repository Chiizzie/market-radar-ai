"""News evidence acceptance, separate from transport/workflow completion."""
from .combine import combine_feeds


def assess_news(macro, company, *, now):
    combined=combine_feeds([macro,company],now=now)
    # Zero results cannot prove company-news delivery, nor does a macro success.
    checks={
        'macro_items_available':combined['sources'][0]['status'] in ('ok','partial') and bool(macro.get('items')),
        'company_items_available':combined['sources'][1]['status'] in ('ok','partial') and bool(company.get('items')),
        'both_sources_usable':all(s['status'] in ('ok','partial') for s in combined['sources'])}
    return {'schema_version':'1.0','tested_at':now.isoformat(),'checks':checks,
        'news_delivery_verified':all(checks.values()),'trade_authorized':False,
        'note':'Delivery checks only; company entity relevance and catalyst significance remain unverified.'}


def main():
    import argparse,json
    from pathlib import Path
    from datetime import datetime,timezone
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--macro',type=Path,required=True)
    parser.add_argument('--company',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    def read(path):
        try:return json.loads(path.read_text())
        except (OSError,ValueError):return {'status':'error','items':[]}
    report=assess_news(read(args.macro),read(args.company),now=datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    return int(not report['news_delivery_verified'])


if __name__=='__main__':raise SystemExit(main())
