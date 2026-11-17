"""Verify bounded v9 Rice parsing on old/new C and real AVR5 ASM.

Requires AVR-GCC, g++, simavr1.6 and libelf; Python standard library only.
Output is confined to a fresh ignored build directory. No media is needed.
"""
from pathlib import Path
import argparse,hashlib,io,json,subprocess,zipfile
REL=Path('Codecs/LPX/01_ACTIVE_Q0_CODEC')
ROOT=next(p for p in Path(__file__).resolve().parents if (p/REL/'src/Lpx4HybridCore.cpp').is_file())
PROGRAM=r'''
#include <avr/io.h>
#include <avr/interrupt.h>
#define private public
#include "Lpx4HybridCore.h"
#undef private
#include "Lpx4HybridCore.cpp"
static Lpx4HybridCore decoder;
extern "C" {
extern const uint8_t probe_feed[2] PROGMEM __attribute__((used,externally_visible))={0x35,0xa6};
extern const uint16_t probe_hardware[] PROGMEM __attribute__((used,externally_visible))={_SFR_MEM_ADDR(SPL),_SFR_MEM_ADDR(SPH),TIMER1_OVF_vect_num};
volatile uint8_t probe_ready,probe_profile,probe_k,probe_width,probe_left,probe_cache,probe_bytes,probe_initial_error;
volatile uint8_t probe_value,probe_end_left,probe_end_cache,probe_error;
volatile uint16_t probe_end_bytes,probe_cursor,probe_irqs;
__attribute__((noinline,used)) void probe_case(){
 decoder.data_=probe_feed;decoder.bytes_=probe_bytes;
 decoder.bitsLeft_=probe_left;decoder.bitBuffer_=probe_cache;
 decoder.error_=(Lpx4HybridCore::Error)probe_initial_error;
 decoder.speechProfile_=probe_profile;
 probe_value=decoder.readSpeechRice(probe_k,probe_width);
 probe_end_left=decoder.bitsLeft_;probe_end_cache=decoder.bitBuffer_;probe_error=decoder.error();
 probe_end_bytes=decoder.bytes_;probe_cursor=(uint16_t)(decoder.data_-probe_feed);
}
}
ISR(TIMER1_OVF_vect){++probe_irqs;}
int main(){TIMSK1=_BV(TOIE1);TCCR1A=_BV(WGM10);TCCR1B=_BV(WGM12)|_BV(CS10);sei();probe_ready=1;for(;;){}}
'''
def sha(p):return hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('output',type=Path);parser.add_argument('--baseline-ref',default='57513b10');parser.add_argument('--wsl')
 args=parser.parse_args();out=args.output.resolve()
 if not out.is_relative_to((ROOT/'build').resolve()) or out==(ROOT/'build').resolve():raise ValueError('Use an ignored build subdirectory')
 if out.exists() and any(out.iterdir()):raise ValueError('Use a fresh output directory')
 out.mkdir(parents=True,exist_ok=True)
 revision=subprocess.check_output(['git','rev-parse','--verify','--end-of-options',args.baseline_ref+'^{commit}'],cwd=ROOT,text=True).strip()
 archive=subprocess.check_output(['git','archive','--format=zip',revision,(REL/'src').as_posix(),(REL/'profiles').as_posix()],cwd=ROOT)
 with zipfile.ZipFile(io.BytesIO(archive)) as z:z.extractall(out/'baseline')
 before=out/'baseline'/REL;after=ROOT/REL
 if sha(before/'src/Lpx4HybridCore.cpp')==sha(after/'src/Lpx4HybridCore.cpp'):raise ValueError('No source transition to verify')
 prefix=['wsl','-d',args.wsl,'--'] if args.wsl else []
 def path(p):
  p=Path(p).resolve()
  return '/mnt/'+p.drive[0].lower()+'/'+ '/'.join(p.parts[1:]) if args.wsl and p.drive else str(p)
 def call(*values):
  r=subprocess.run([*prefix,*map(str,values)],capture_output=True)
  if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace'))
  return r.stdout
 if call('pkg-config','--modversion','simavr').decode().strip()!='1.6':raise ValueError('This context adapter requires simavr1.6')
 (out/'probe.cpp').write_text(PROGRAM,newline='\n');bindings={}
 for label,port in [('old',before),('new',after)]:
  for backend,asm in [('asm',1),('c',0)]:
   name=label+'-'+backend;output=out/name
   flags=['-mmcu=atmega328p','-DF_CPU=16000000UL','-Os','-flto','-std=c++11','-fno-exceptions','-fno-rtti','-ffunction-sections','-fdata-sections',f'-DLPX4_ENABLE_ASM={asm}','-DLPX4_FLOAT_SYNTHESIS=0','-DLPX4_COMPACT_VERSION=9','-DLPX3_LPC_SEGMENTS=2','-ffixed-r10','-ffixed-r11']
   call('avr-g++',*flags,'-include',path(port/'profiles/Lpx4Sram512.h'),'-I'+path(port/'src'),path(out/'probe.cpp'),'-Wl,--gc-sections','-Wl,--undefined=probe_case','-Wl,--undefined=probe_hardware','-o',path(output.with_suffix('.elf')))
   call('avr-objcopy','-O','binary',path(output.with_suffix('.elf')),path(output.with_suffix('.bin')))
   bindings[name]=dict(core_text_lf_sha256=sha(port/'src/Lpx4HybridCore.cpp'),header_text_lf_sha256=sha(port/'src/Lpx4HybridCore.h'),profile_text_lf_sha256=sha(port/'profiles/Lpx4Sram512.h'),binary_sha256=hashlib.sha256(output.with_suffix('.bin').read_bytes()).hexdigest())
 if (out/'old-c.bin').read_bytes()!=(out/'new-c.bin').read_bytes():raise ValueError('Explicit C binary changed')
 if (out/'old-asm.bin').read_bytes()==(out/'new-asm.bin').read_bytes():raise ValueError('No changed AVR5 Rice implementation was selected')
 observer=Path(__file__).with_name('rice_packet_observer.c')
 call('gcc','-O2','-std=c11','-I/usr/include/simavr',path(observer),'-lsimavr','-lelf','-o',path(out/'sim-proof'))
 (out/'native.log').write_bytes(call(path(out/'sim-proof'),path(out)))
 result=json.loads((out/'verification.json').read_text())
 result.update(baseline_revision=revision,compiler=call('avr-g++','--version').decode().splitlines()[0],simavr='1.6',explicit_c_binary_exact=True,source_binding=bindings,probe_text_lf_sha256=sha(out/'probe.cpp'),driver_text_lf_sha256=sha(Path(__file__)),observer_text_lf_sha256=sha(observer),private_reader_error_note='Paired old/new traces match with error0/4. Cross-backend equality is required from a clear error state; the predecessor difference for calls to the private reader with an already-set error remains unchanged.')
 (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:result[k] for k in ['cases_per_backend','backends','successful_traces','error_traces','explicit_c_binary_exact']}))
if __name__=='__main__':main()
