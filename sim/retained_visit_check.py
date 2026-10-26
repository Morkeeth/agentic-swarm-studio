"""Replay one successful retained read-only visitor path without another model call.

Bounded local regression candidate: reproduces recorded navigation and requires
its quoted result on the actual final page. It does not validate general meaning,
unobserved tasks, write flows, or an independent human outcome.
"""
import argparse,json,re
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from sim.app_swarm import quote_on_page

def replay(record, output):
    raw=json.loads(Path(record).read_text());v=raw.get('visitor',raw)
    if not v.get('confirmed') or v.get('outcome')!='got_there':raise ValueError('Only a confirmed completed retained visit can create this check.')
    steps=v['steps'];start=steps[0]['url'];u=urlsplit(start)
    if u.scheme!='http' or u.hostname not in ('127.0.0.1','localhost','::1'):raise ValueError('Only an owned loopback target is allowed.')
    quote=next((s.get('claim_evidence') for s in reversed(steps) if s.get('claim_evidence')),None)
    if not quote:raise ValueError('No retained quoted completion evidence.')
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    result={'schema':'retained-local-regression/1','source_visit':Path(record).parent.name,'url':start,'model_calls':0,'status':'failed','actions':[]}
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True);context=browser.new_context(viewport={'width':1440,'height':900})
            def read_only(route):
                req=route.request;ru=urlsplit(req.url)
                if req.method!='GET' or (ru.scheme in ('http','https') and ru.netloc!=u.netloc):return route.abort()
                return route.continue_()
            context.route('**/*',read_only);page=context.new_page();page.set_default_timeout(8000)
            response=page.goto(start,wait_until='domcontentloaded')
            if not response or response.status>=400:raise AssertionError('Starting page did not load.')
            for i,s in enumerate(steps):
                action=s.get('action')
                if action=='click':
                    target=page.get_by_role('link',name=s['target_text'],exact=True)
                    if target.count()!=1:raise AssertionError('Recorded link is missing or ambiguous: '+s['target_text'])
                    target.click();page.wait_for_timeout(250)
                elif action=='back':page.go_back(wait_until='domcontentloaded')
                elif action=='scroll':page.evaluate('window.scrollBy(0,Math.round(innerHeight*.85))')
                elif action=='done':pass
                else:raise ValueError('Unsupported recorded action: '+str(action))
                page.screenshot(path=str(out/f'step-{i+1:02d}.png'))
                result['actions'].append({'action':action,'url':page.url,'target':s.get('target_text')})
            if page.url!=steps[-1]['url']:raise AssertionError('Final address differs from the retained visit.')
            if not quote_on_page(quote,page.locator('body').inner_text()):raise AssertionError('Retained quoted answer is absent from the current page.')
            result.update(status='passed',final_url=page.url,quoted_evidence=quote)
            context.close();browser.close()
    except Exception as e:result['reason']=type(e).__name__+': '+str(e)[:400]
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--record',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    r=replay(a.record,a.output);print(json.dumps(r));raise SystemExit(0 if r['status']=='passed' else 1)
