"""Export only the exact allowlisted files of one pinned commit; never publish."""
import argparse,hashlib,json,re,subprocess,tarfile
from pathlib import Path,PurePosixPath

def export(sha,output):
    if not re.fullmatch(r'[0-9a-f]{40}',sha):raise ValueError('An exact40character commit is required.')
    root=Path(__file__).resolve().parents[1]
    lines=subprocess.check_output(['git','show',sha+':SOURCE-ALLOWLIST.txt'],cwd=root,text=True).splitlines()
    files=[x.strip() for x in lines if x.strip() and not x.startswith('#')]
    if len(files)!=len(set(files)):raise ValueError('Duplicate allowlist entry.')
    for name in files:
        p=PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or name.startswith(('submission/','.git/')):raise ValueError('Unsafe public source entry.')
    out=Path(output);out.mkdir(parents=True,exist_ok=False);hashes={}
    proc=subprocess.Popen(['git','archive',sha,'--',*files],cwd=root,stdout=subprocess.PIPE)
    try:
        with tarfile.open(fileobj=proc.stdout,mode='r|') as archive:
            for member in archive:
                if member.isdir():continue
                if member.name not in files or not member.isfile():raise ValueError('Unexpected archive member: '+member.name)
                target=out/member.name;target.parent.mkdir(parents=True,exist_ok=True)
                source=archive.extractfile(member);digest=hashlib.sha256()
                with target.open('wb') as stream:
                    while block:=source.read(65536):stream.write(block);digest.update(block)
                target.chmod(0o755 if member.mode & 0o111 else 0o644)
                hashes[member.name]=digest.hexdigest()
        if proc.wait()!=0:raise RuntimeError('Pinned git archive failed.')
    finally:
        if proc.poll() is None:proc.kill();proc.wait()
    if set(hashes)!=set(files):raise ValueError('Archive did not exactly match the allowlist.')
    receipt={'schema':'public-source-export/1','source_sha':sha,'file_count':len(hashes),'files':hashes,'submission_included':False,'git_history_included':False}
    out.with_name(out.name+'-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-sha',required=True);p.add_argument('--output',required=True);a=p.parse_args();r=export(a.source_sha,a.output);print(json.dumps({'source_sha':r['source_sha'],'file_count':r['file_count']}))
