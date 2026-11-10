import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--avr-gcc',required=True);p.add_argument('--variant',default='loop',choices=['loop','inline','separate','shared']);p.add_argument('--order',default='both',choices=['8','10','both']);p.add_argument('--backend',default='asm',choices=['asm','c','generic']);a=p.parse_args()
compiler=Path(a.avr_gcc).resolve();prefix=str(compiler.with_name('avr-'));ext=compiler.suffix
common=['-std=c11','-Os','-flto','-fno-ipa-icf','-fwrapv','-fno-strict-aliasing','-ffunction-sections','-fdata-sections','-mmcu=atmega328p','-mcall-prologues','-mrelax','-I'+str(ROOT/'src'),'-DSPEEX_NB3_ENABLE_ASM='+str(int(a.backend!='c'))]
if a.backend=='generic':common+=['-DSPEEX_NB3_ARCH=SPEEX_NB3_ARCH_GENERIC']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def srcsha(p):return hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
for order in ([8,10] if a.order=='both' else [int(a.order)]):
 source={'inline':'lsp_finish_inline.S','loop':'lsp_finish_loop.S','shared':'lsp_finish_shared.S','separate':f'lsp_finish{order}.S'}[a.variant]
 fixture='fixture.c' if order==8 else 'fixture10.c';out=ROOT/f'{a.variant}{order}-{a.backend}';out.mkdir(exist_ok=True)
 subprocess.run([compiler,*common,ROOT/fixture,ROOT/'src'/source,'-Wl,--gc-sections','-o',out/'unit.elf'],check=True)
 subprocess.run([prefix+'objcopy'+ext,'-O','binary','-R','.eeprom',out/'unit.elf',out/'unit.bin'],check=True)
 for tool,file,flags in [('nm','symbols.txt',['-n','-S']),('objdump','disassembly.txt',['-d'])]:
  (out/file).write_text(subprocess.check_output([prefix+tool+ext,*flags,out/'unit.elf'],text=True),encoding='utf-8')
 # Verifier reads the unsized nm format; size symbols have their own artifact.
 (out/'sizes.txt').write_text((out/'symbols.txt').read_text(),encoding='utf-8')
 (out/'symbols.txt').write_text(subprocess.check_output([prefix+'nm'+ext,'-n',out/'unit.elf'],text=True),encoding='utf-8')
 sources=[ROOT/fixture,ROOT/'src'/source,ROOT/'src/nb3_lsp_finish.h',ROOT/'src/speex_platform.h']
 (out/'input.json').write_text(json.dumps(dict(backend=a.backend,variant=a.variant,order=order,binarySha256=sha(out/'unit.bin'),savedRegisters={'inline':16,'loop':16,'shared':15,'separate':14}[a.variant],stackBytes={'inline':16,'loop':18,'shared':15,'separate':14}[a.variant],options=common,compilerSha256=sha(compiler),sourceSha256={str(p.relative_to(ROOT)):srcsha(p) for p in sources}),indent=2)+'\n',encoding='utf-8')
 print(out.name,len((out/'unit.bin').read_bytes()),sha(out/'unit.bin'))
