"""Operator-only import of a local Codex diagnostic into the existing studio.

No web endpoint, auth file, transcript, model call or sponsor evidence is added.
The local store is outside the source/export tree and remains a private review.
"""
import argparse,copy,json,re,shutil
from pathlib import Path
from sim import studio_test

def import_visit(record,store,run_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',run_id):raise ValueError('Invalid run id.')
    source=Path(record).resolve();raw=json.loads(source.read_text())
    if raw.get('schema')!='codex-subscription-visitor/1':raise ValueError('Not a Codex diagnostic receipt.')
    row=copy.deepcopy(raw['visitor']);out=Path(store)/'runs'/run_id;out.mkdir(parents=True,exist_ok=False)
    for step in row.get('steps',[]):
        for shot in [step.get('screenshot'),(step.get('hit') or {}).get('screenshot')]:
            if not shot:continue
            if Path(shot).name!=shot:raise ValueError('Invalid screenshot name.')
            f=source.parent/shot
            if f.is_symlink() or f.resolve().parent!=source.parent:raise ValueError('Screenshot escaped the retained visit.')
            shutil.copyfile(f,out/shot)
    result={'id':run_id,'url':row['steps'][0]['url'],'job':{'text':row['goal'],'source':'you'},'status':'complete',
            'diagnostic':'Local Codex subscription diagnostic, not NVIDIA/Nebius runtime evidence.',
            'provider':raw['provider'],'model':'Codex CLI; resolved model not reported','judge_model':None,
            'tries':[[row]],'tries_planned':1,'visitors':[row],'headline':'Local diagnostic: '+str(row['outcome']),
            'model_calls':raw['subscription_calls'],'spend':{'calls':raw['calls'],'model_calls':raw['subscription_calls'],'billing_channel':'ChatGPT subscription','listed_rate_estimate_usd':None},
            'limitations':raw['limits']+['Imported retained diagnostic; viewing this run makes no model call.','Same-model confirmation is not an independent visual judge.']}
    test=studio_test.generate(result)
    if test:(out/'test_swarm_path.py').write_text(test)
    result['handed_back_test']=bool(test)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return out
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--record',required=True);p.add_argument('--store',required=True);p.add_argument('--run-id',required=True);a=p.parse_args();print(import_visit(a.record,a.store,a.run_id))
