from pathlib import Path
import difflib,hashlib,json,shutil,subprocess
ROOT=Path(__file__).resolve().parent;CODEC=ROOT.parents[1]
OUT=ROOT/'candidate';OUT.mkdir(exist_ok=True)
def digest(data):return hashlib.sha256(data.replace(b'\r\n',b'\n')).hexdigest()
def baseline(name):return subprocess.check_output(['git','show','e5350100:Codecs/Speex/AVR/src/'+name],cwd=CODEC).replace(b'\r\n',b'\n')
for source,target in [('src/lsp_finish_loop.S','lsp_finish.S'),('src/nb3_lsp_finish.h','nb3_lsp_finish.h')]:
 shutil.copyfile(ROOT/source,OUT/target)
s=baseline('compact_lsp.c.inc').decode('utf-8')
before='    spx_word32_t p[5],q[5],previous_p=0,previous_q=0;\n    int j;'
assert s.count(before)==1
s=s.replace(before,'    spx_word32_t p[5],q[5];')
before='    for(j=1;j<=8;j++) {\n        int index=j<=4?j:8-j;\n        spx_word32_t a=PSHR32(p[index]+previous_p+q[index]-previous_q,8);\n        previous_p=p[index];previous_q=q[index];\n        if(a< -32767)a=-32767;if(a>32767)a=32767;ak[j-1]=(int16_t)a;\n    }'
assert s.count(before)==1
s=s.replace(before,'    speex_nb3_lsp_finish8(p,q,ak);')
(OUT/'compact_lsp.c.inc').write_text(s,encoding='utf-8')
patch=''
for name in ['lsp_finish.S','nb3_lsp_finish.h','compact_lsp.c.inc']:
 old=baseline(name).decode('utf-8').splitlines(keepends=True);new=(OUT/name).read_text(encoding='utf-8').splitlines(keepends=True)
 patch+=''.join(difflib.unified_diff(old,new,fromfile='a/Codecs/Speex/AVR/src/'+name,tofile='b/Codecs/Speex/AVR/src/'+name))
(ROOT/'candidate.patch').write_text(patch,encoding='utf-8')
(ROOT/'candidate-manifest.json').write_text(json.dumps(dict(scope='Isolated tested candidate; no production files changed',sourceHashConvention='SHA256 UTF-8 LF; trailing newline preserved',candidate={name:digest((OUT/name).read_bytes()) for name in ['lsp_finish.S','nb3_lsp_finish.h','compact_lsp.c.inc']},base={name:digest(baseline(name)) for name in ['lsp_finish.S','nb3_lsp_finish.h','compact_lsp.c.inc']}),indent=2)+'\n',encoding='utf-8')
print('Prepared existing-file candidate replacements and unified patch; production untouched')
