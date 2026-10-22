import subprocess, pathlib, re, numpy as np, shutil, json
ROOT=pathlib.Path(__file__).resolve().parent
DATA={
 'chego':ROOT/'MicroMusic_AdaptiveLPC8/adaptive_results/xtuj-ntt/trained_parameters.npz',
 'otvechaesh':ROOT/'MicroMusic_AdaptiveLPC8/adaptive_results/ne-otv/trained_parameters.npz',
 'vinni':ROOT/'MicroMusic-TinyLPC-v5/best_parameters.npz'
}
CHIRPS={
 'nano': ''' cpi r18,1\n breq pulse_second\n clr r18\n rjmp filter\npulse_second:\n mov r18,r3\n neg r18\n rjmp filter\n''',
 'full': ''' cpi r18,1\n breq pulse_second\n cpi r18,2\n breq pulse_third\n cpi r18,3\n breq pulse_fourth\n clr r18\n rjmp filter\npulse_second:\n mov r18,r3\n lsl r18\n add r18,r3\n rjmp filter\npulse_third:\n mov r18,r3\n lsl r18\n rjmp filter\npulse_fourth:\n mov r18,r3\n neg r18\n rjmp filter\n'''
}
# For initial experiment 'soft' applies softened 4-tap excitation, a distinct impulse.
CHIRPS['soft']=''' cpi r18,1\n breq pulse_second\n cpi r18,2\n breq pulse_third\n cpi r18,3\n breq pulse_fourth\n clr r18\n rjmp filter\npulse_second:\n mov r18,r3\n lsl r18\n rjmp filter\npulse_third:\n mov r18,r3\n rjmp filter\npulse_fourth:\n mov r18,r3\n neg r18\n rjmp filter\n'''

def run(cmd,cwd): subprocess.run(cmd,cwd=cwd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
def build(phrase,variant):
 wd=ROOT/'mini_build'/phrase/variant
 wd.mkdir(parents=True,exist_ok=True)
 d=np.load(DATA[phrase]); K=d['K'];P=d['P'];E=d['E']; n=len(P)
 if K.shape[1]==7:K=np.column_stack([K,np.zeros(n,dtype=int)])
 packed=bytearray()
 for i in range(n):
  packed.extend((int(P[i]),int(E[i])))
  for j in range(0,8,2):
   packed.append((int(K[i,j])+8)|((int(K[i,j+1])+8)<<4))
 speech=bytes(packed)
 (wd/'voice_tinylpc.bin').write_bytes(speech)
 t=(ROOT/'mini_template.S').read_text().replace('__CHIRP_BODY__',CHIRPS[variant])
 t=t.replace('__VOICE_ADDR__','0x03e0')
 (wd/'tinylpc.S').write_text(t)
 run(['clang','-target','avr','-mmcu=attiny13','-c','tinylpc.S','-o','test.o'],wd)
 syms=subprocess.check_output(['llvm-objdump','-t','test.o'],cwd=wd,text=True)
 m=re.search(r'([a-f0-9]{8})\s+\w+\s+\.text\s+\S+\s+code_end',syms)
 if not m:
  print(syms[-700:]); raise Exception('code_end not found')
 code=int(m.group(1),16)
 t=t.replace('0x03e0',hex(code))
 (wd/'tinylpc.S').write_text(t)
 run(['clang','-target','avr','-mmcu=attiny13','-c','tinylpc.S','-o','tinylpc.o'],wd)
 syms=subprocess.check_output(['llvm-objdump','-r','tinylpc.o'],cwd=wd,text=True)
 if 'R_AVR_' in syms: raise Exception('relocs '+syms)
 run(['llvm-objcopy','-O','binary','tinylpc.o','tinylpc.bin'],wd)
 firmware=(wd/'tinylpc.bin').read_bytes()
 print(phrase,variant,'code',code,'speech',len(speech),'firmware',len(firmware))
 if len(firmware)>1024:
  return None
 lines=[]
 for addr in range(0,len(firmware),16):
  part=firmware[addr:addr+16];row=bytearray([len(part),addr>>8,addr&255,0])+part
  lines.append(':'+row.hex().upper()+f'{-sum(row)&255:02X}')
 lines.append(':00000001FF')
 (wd/'tinylpc.hex').write_text('\n'.join(lines)+'\n')
 return dict(phrase=phrase,variant=variant,code=code,speech=len(speech),flash=len(firmware),frames=n,dir=str(wd))

if __name__=='__main__':
 results=[]
 for p in DATA:
  for v in CHIRPS:
   try:
    a=build(p,v)
    if a:results.append(a)
   except Exception as e:print('ERR',p,v,str(e))
 (ROOT/'mini_build'/'status.json').write_text(json.dumps(results,indent=2))
