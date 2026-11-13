"""Stdlib-only rebuild proof for the exact shipped LPX ASM images.

Default only checks the public plan; --run must be explicitly selected after
final source readiness. No catalog, HEX, source/header override or IRQ rerun.
"""
from pathlib import Path
import argparse,ast,hashlib,importlib.util,json,re,subprocess,sys
ACTIVE=Path(__file__).resolve().parents[1]
ROOT=ACTIVE.parents[2]
WEB=ROOT/'web-player'

def sha(b):return hashlib.sha256(b).hexdigest()
def textsha(b):return sha(b.replace(b'\r\n',b'\n'))
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def ast_exports(path,assignments=(),functions=()):
 tree=ast.parse(path.read_text(encoding='utf-8'));body=[];found=set()
 for node in tree.body:
  names={t.id for t in node.targets if isinstance(t,ast.Name)} if isinstance(node,ast.Assign) else {node.name} if isinstance(node,ast.FunctionDef) else set()
  selected=names&set(assignments) if isinstance(node,ast.Assign) else names&set(functions)
  if selected:body.append(node);found|=selected
 if found!=set(assignments)|set(functions):raise ValueError('Original build recipe exports changed')
 ns={};exec(compile(ast.Module(body=body,type_ignores=[]),str(path),'exec'),ns);return ns

def hex_bytes(data,limit):
 memory=bytearray(b'\xff'*limit);present=set();end=0;eof=False
 for line in data.decode('ascii').strip().split():
  if eof or not re.fullmatch(r':(?:[0-9a-fA-F]{2})+',line):raise ValueError('Invalid HEX record')
  b=bytes.fromhex(line[1:]);n=b[0];at=int.from_bytes(b[1:3],'big');kind=b[3]
  if len(b)!=n+5 or sum(b)&255:raise ValueError('Invalid HEX length/checksum')
  if kind==1:
   if n or at:raise ValueError('Invalid HEX EOF')
   eof=True
  elif kind==0:
   if at+n>limit or any(i in present for i in range(at,at+n)):raise ValueError('Invalid HEX range')
   memory[at:at+n]=b[4:4+n];present.update(range(at,at+n));end=max(end,at+n)
  else:raise ValueError('Unexpected HEX record type')
 if not eof or not end or len(present)!=end:raise ValueError('Incomplete HEX image')
 return bytes(memory[:end])

def plan():
 jobs=[]
 for family,name in [('tiny','firmware-lpx-attiny88.json'),('nano','firmware-atmega328p.json')]:
  catalog=read(WEB/name)
  for variant in catalog['variants']:
   clip=next(c for c in catalog['clips'] if c['clipId']==variant['clipId'])
   preview=next(v for v in clip['variants'] if v['id']==variant['id'])
   source=WEB/variant['source'];stream=WEB/preview['stream'];hexdata=source.read_bytes();blob=stream.read_bytes()
   assert sha(hexdata)==variant['hexSha256'] and sha(blob)==variant['streamSha256']
   assert len(hex_bytes(hexdata,8192 if family=='tiny' else 30720))==variant['flashBytes']
   gain=(variant.get('outputLevel') or preview['outputLevel'])['numerator']
   if 'outputLevel' in preview:assert gain==preview['outputLevel']['numerator']
   jobs.append(dict(family=family,id=variant['clipId']+'-'+variant['id'],hex=source,streams=[stream],
    gain=gain,low15=variant['id']=='low15',flash=variant['flashBytes'],program=variant['programFlashBytes'],catalog=WEB/name))
 dialogue=read(WEB/'audio/lpx-dialogue/manifest.json');hexfile=WEB/dialogue['firmware']
 assert sha(hexfile.read_bytes())==dialogue['hexSha256']
 streams=[WEB/s['stream'] for s in dialogue['segments']]
 for p,s in zip(streams,dialogue['segments']):assert sha(p.read_bytes())==s['streamSha256']
 jobs.append(dict(family='dialogue',id='dialogue-quality',hex=hexfile,streams=streams,gain=dialogue['outputLevel']['numerator'],low15=False,
  flash=dialogue['flashBytes'],program=dialogue['programFlashBytes'],catalog=WEB/'audio/lpx-dialogue/manifest.json'))
 assert sum(j['family']=='tiny' for j in jobs)==9 and sum(j['family']=='nano' for j in jobs)==8 and sum(j['family']=='dialogue' for j in jobs)==1
 return jobs

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);parser.add_argument('--wsl');parser.add_argument('--run',action='store_true');args=parser.parse_args()
 out=args.output.resolve()
 if not out.is_relative_to((ROOT/'build').resolve()):raise ValueError('Use ignored build storage')
 if out.exists() and any(out.iterdir()):raise ValueError('Use a fresh output directory')
 out.mkdir(parents=True,exist_ok=True);jobs=plan()
 recipe=ast_exports(ACTIVE/'tools/benchmark_speech_flash.py',('BASE','LTO','GC','CALL','RELAX','CANDIDATES'),('candidate','command_flags'))
 voice=ast_exports(ACTIVE/'tools/measure_speech_firmware.py',functions=('voice_header',))['voice_header']
 spec=recipe['CANDIDATES']['unroll1-tune0-lto-call-relax']
 assert spec==dict(unroll=1,tuning=0,flags=['-flto','-mcall-prologues','-mrelax'])
 summary=dict(schema='lpx-shipped-asm-equivalence-v1',prepared=True,builds_performed=False,tiny_images=9,nano_images=8,dialogue_images=1,
  source_header_overrides=False,physical_board_measured=False,new_irq_measurement=False,
  scope='Exact rebuilt current linked ASM binaries compared with decoded shipped public HEX; old catalogs/timing receipts stay unchanged')
 (out/'plan.json').write_text(json.dumps(summary,indent=2)+'\n')
 if not args.run:print('Prepared18 public-image comparisons; no compilation performed.');return
 prefix=['wsl','-d',args.wsl,'--'] if args.wsl else []
 def target(p):
  p=Path(p).resolve()
  return '/mnt/'+p.drive[0].lower()+'/'+ '/'.join(p.parts[1:]) if args.wsl and p.drive else str(p)
 def command(*values):
  r=subprocess.run([*prefix,*map(str,values)],capture_output=True)
  if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace'))
  return r.stdout
 sources=[Path(__file__),*sorted((ACTIVE/'src').rglob('*')),*sorted((ROOT/'Codecs/common').rglob('*')),
  ACTIVE/'profiles/Lpx4Sram512.h',ACTIVE/'examples/ATTINY88_V5_PLAYER/player.cpp',ACTIVE/'examples/AVR_V5_PLAYER/player.cpp',
  ACTIVE/'examples/AVR_V5_PLAYER/player_config.h',ACTIVE/'tools/build_attiny88_player.py',ACTIVE/'tools/build_release_player.py',
  ACTIVE/'tools/benchmark_speech_flash.py',ACTIVE/'tools/measure_speech_firmware.py',
  ROOT/'ATtiny88/Music/universal/vendor/ATtiny_DFP/3.4.278/include/avr/iotn88.h']
 sources=[p for p in sources if p.is_file()];binding={p.relative_to(ROOT).as_posix():textsha(p.read_bytes()) for p in sources}
 protected={p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for j in jobs for p in (j['hex'],j['catalog'],*j['streams'])}
 sys.path.insert(0,str(ACTIVE/'tools'));import build_attiny88_player as tiny
 rows=[]
 for job in jobs:
  folder=out/job['family']/job['id'];folder.mkdir(parents=True,exist_ok=True);blobs=[p.read_bytes() for p in job['streams']]
  if job['family']=='tiny':
   cost=tiny.build(job['streams'][0],folder,wsl=args.wsl,assembly=True,asm_isr=True,queue=24,mul16_unroll=2,output_gain=job['gain'],sparse80=job['low15'],universal=False)
   binary=(folder/'player.bin').read_bytes();flags=cost['compiler_options']
  else:
   settings={**recipe['BASE'],'queue':256,'prefill':192};env=dict(settings=settings,compact_only=True,retained_profile_symbols=[])
   flags=recipe['command_flags'](env,spec,True,0)
   flags=[f for f in flags if not f.startswith(('-DLPX4_PROFILE_QUEUE=','-DLPX4_PROFILE_PREFILL=','-DLPX4_PROFILE_IRQ_LOAD='))]
   if job['low15']:flags+=['-DLPX4_ENABLE_SPARSE80=1']
   flags += ['-DLPX_PLAYER_QUEUE=256','-DLPX_PLAYER_PREFILL=192','-DLPX_PLAYER_IRQ_LOAD=0','-DLPX_PLAYER_DATA_HEADER="voice_data.h"',f'-DPWM_GAIN_Q7={job["gain"]}']
   (folder/'voice_data.h').write_text(voice(blobs).replace('profile_','lpx_')+f'#define LPX_PLAYER_SEGMENTS {len(blobs)}\n',encoding='utf-8',newline='\n')
   command('avr-g++',*flags,'-I'+target(ACTIVE/'src'),'-I'+target(ACTIVE/'examples/AVR_V5_PLAYER'),'-I'+target(folder),
    target(ACTIVE/'examples/AVR_V5_PLAYER/player.cpp'),target(ACTIVE/'src/Lpx4HybridCore.cpp'),'-Wl,-Map='+target(folder/'player.map'),'-o',target(folder/'player.elf'))
   command('avr-objcopy','-O','binary','-R','.eeprom',target(folder/'player.elf'),target(folder/'player.bin'))
   command('avr-objcopy','-O','ihex','-R','.eeprom',target(folder/'player.elf'),target(folder/'player.hex'))
   binary=(folder/'player.bin').read_bytes()
  symbols=command('avr-nm','-S','--defined-only',target(folder/'player.elf')).decode()
  (folder/'player-defined.nm').write_text(symbols)
  float_symbols=[line.split()[-1] for line in symbols.splitlines() if line.split() and (re.search(r'^(?:__fp_|__(?:add|sub|mul|div|cmp|eq|ne|lt|le|gt|ge|unord|fix|float|extend|trunc).*(?:sf|df))',line.split()[-1]) or 'lpx4Float' in line.split()[-1] or line.split()[-1] in ('floor','floorf','sin','sinf','cos','cosf','sqrt','sqrtf','pow','powf'))]
  shipped=hex_bytes(job['hex'].read_bytes(),8192 if job['family']=='tiny' else 30720)
  row=dict(family=job['family'],id=job['id'],current_binary_sha256=sha(binary),shipped_binary_sha256=sha(shipped),
   shipped_hex_sha256=sha(job['hex'].read_bytes()),binary_exact=binary==shipped,flash_bytes=len(binary),shipped_flash_bytes=len(shipped),
   embedded_audio_bytes=sum(map(len,blobs)),program_bytes=len(binary)-sum(map(len,blobs)),stored_gain_numerator=job['gain'])
  row['declared_size_matches']=len(shipped)==job['flash'] and row['program_bytes']==job['program']
  row['no_float_runtime_symbols']=not float_symbols;row['float_runtime_symbols']=float_symbols
  row['compiler_options']=[f.replace(target(ROOT),'<repo>') for f in flags]
  rows.append(row);(out/'progress.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps({k:row[k] for k in ('family','id','binary_exact','flash_bytes','shipped_flash_bytes')}),flush=True)
 for name,digest in binding.items():assert textsha((ROOT/name).read_bytes())==digest,'Sources changed during equivalence build'
 for name,digest in protected.items():assert sha((ROOT/name).read_bytes())==digest,'Shipped artifact changed'
 summary.update(builds_performed=True,current_source_sha256=binding,shipped_artifact_sha256=protected,cases=rows,
  all_binaries_exact=all(r['binary_exact'] for r in rows),all_no_float_runtime_symbols=all(r['no_float_runtime_symbols'] for r in rows),all_declared_sizes_exact=all(r['declared_size_matches'] for r in rows),compiler=command('avr-g++','--version').decode().splitlines()[0])
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 if not summary['all_binaries_exact']:raise SystemExit(2)
if __name__=='__main__':main()
