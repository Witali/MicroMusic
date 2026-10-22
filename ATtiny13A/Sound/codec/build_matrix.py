import pathlib,re,subprocess,numpy as np,json,sys
R=pathlib.Path(__file__).resolve().parent
BASE=(R/'mini_template.S').read_text()
exec((R/'build_mini.py').read_text().split("if __name__")[0])

def do(cmd,cwd):
 try: subprocess.run(cmd,cwd=cwd,check=True,capture_output=True)
 except subprocess.CalledProcessError as e:raise RuntimeError(e.stderr.decode())

def source_for(flavor):
 s=BASE.replace('__CHIRP_BODY__',CHIRPS['full'])
 # 3-bit shift-add signed MAC; constant worst-case cost vs variable repeated additions.
 s=s.replace("mul_loop:\n add r24,r16\n adc r0,r17\n dec r25\n brne mul_loop", """ sbrs r25,0
 rjmp mult_skip1
 add r24,r16
 adc r0,r17
mult_skip1:
 lsl r16
 rol r17
 sbrs r25,1
 rjmp mult_skip2
 add r24,r16
 adc r0,r17
mult_skip2:
 lsl r16
 rol r17
 sbrs r25,2
 rjmp mult_skip3
 add r24,r16
 adc r0,r17
mult_skip3:""")
 # input frames have short flag in pitch byte, and gain with bit7 for speed in adaptive
 # change decoding header and possible early return
 s=s.replace('read_pitch:\n mov r4,r16\n mov r2,r16\n lpm r3,Z+', '''read_pitch:
 mov r24,r16
 andi r16,0x7f
 mov r4,r16
 mov r2,r16
 lpm r3,Z+''')
 s=s.replace(' ldi r28,COEFF\n clr r29\n ldi r19,4\nread_k:', ''' sbrc r24,7
 ret
 ldi r28,COEFF
 clr r29
 ldi r19,4
read_k:''')
 if flavor=='adaptive':
  s=s.replace('.set STATE,0x70', '.set STATE,0x70\n.set TARGET,0x78')
  s=s.replace('ldi r28,STATE\n clr r29\n ldi r19,8', 'ldi r28,COEFF\n clr r29\n ldi r19,24',1)
  s=s.replace(' brne current_frame\n rcall read_frame\ncurrent_frame:\n tst r4', ''' brne current_frame
 rcall read_frame
current_frame:
 mov r16,r5
 and r16,r7
 brne smooth_done
 rcall smooth_formants
smooth_done:
 tst r4''',1)
  s=s.replace(' lpm r3,Z+\n sbrc r24,7', ''' lpm r16,Z+
 mov r3,r16
 mov r7,r16
 ldi r16,7
 sbrc r7,7
 ldi r16,3
 mov r7,r16
 ldi r16,0x7f
 and r3,r16
 sbrc r24,7''')
  s=s.replace(' ldi r28,COEFF\n clr r29\n ldi r19,4\nread_k:', ''' ldi r28,TARGET
 clr r29
 ldi r19,4
read_k:''')
  s=s.replace('read_frame:\n', '''/* Slew eight 4-bit reflection coefficients toward target at controlled intervals. */
smooth_formants:
 ldi r26,COEFF
 clr r27
 ldi r28,TARGET
 clr r29
 ldi r19,8
smooth_loop:
 ld r16,X
 ld r17,Y
 cp r16,r17
 breq smooth_next
 brlt smooth_inc
 dec r16
 rjmp smooth_store
smooth_inc:
 inc r16
smooth_store:
 st X,r16
smooth_next:
 inc r26
 inc r28
 dec r19
 brne smooth_loop
 ret
read_frame:
''')
  # need support LD X, LD Y, ST X and add their js support
 # Mask pitch byte with 0x7F for normal frames; silence not special
 return s

def keyframes(K, max_step=3,threshold=13):
 n=len(K);mask=np.zeros(n,dtype=np.uint8);last=0;mask[0]=1
 for i in range(1,n):
  dd=np.abs(K[i]-K[last]);
  if i-last>=max_step or np.sum(dd)>=threshold or np.max(dd)>=6:
   mask[i]=1;last=i
 return mask

def compile_matrix(phrase,flavor):
 wd=R/'new_matrix'/phrase/flavor;wd.mkdir(parents=True,exist_ok=True)
 d=np.load(DATA[phrase]);K=d['K'];P=d['P'];E=d['E'];n=len(P)
 if K.shape[1]==7:K=np.column_stack([K,np.zeros(n,dtype=int)])
 mask=keyframes(K,max_step=3,threshold=18)
 if phrase=='vinni': mask=keyframes(K,max_step=3,threshold=16)
 # Short frame means coefficients carried over; target as previous
 packed=bytearray()
 for i in range(n):
  # high-bit = shorter frame, leave pitch lower7
  packed.append(int(P[i])|(0 if mask[i] else 0x80))
  gain=int(E[i]); assert 0<=gain<=15
  if flavor=='adaptive':
   # choose fast when local rapid spectral changes
   fast=(i==0 or np.sum(np.abs(K[i]-K[i-1]))>=(29 if phrase=="vinni" else 18))
   if fast:gain |= 0x80
  packed.append(gain)
  if mask[i]:
   for j in range(0,8,2):packed.append((int(K[i,j])+8)|((int(K[i,j+1])+8)<<4))
 (wd/'voice_tinylpc.bin').write_bytes(packed)
 s=source_for(flavor).replace('__VOICE_ADDR__','0x03e0')
 (wd/'tinylpc.S').write_text(s)
 do(['clang','-target','avr','-mmcu=attiny13','-c','tinylpc.S','-o','pre.o'],wd)
 syms=subprocess.check_output(['llvm-objdump','-t','pre.o'],cwd=wd,text=True)
 m=re.search(r'([a-f0-9]{8})\s+\w+\s+\.text\s+\S+\s+code_end',syms)
 if not m: raise RuntimeError('code_end not found')
 code=int(m.group(1),16)
 s=s.replace('0x03e0',hex(code))
 (wd/'tinylpc.S').write_text(s)
 do(['clang','-target','avr','-mmcu=attiny13','-c','tinylpc.S','-o','tinylpc.o'],wd)
 rel=subprocess.check_output(['llvm-objdump','-r','tinylpc.o'],cwd=wd,text=True)
 assert 'R_AVR_' not in rel
 do(['llvm-objcopy','-O','binary','tinylpc.o','tinylpc.bin'],wd)
 fw=(wd/'tinylpc.bin').read_bytes()
 if len(fw)>1024: raise ValueError(f'over 1024 ({len(fw)})')
 lines=[]
 for addr in range(0,len(fw),16):
  part=fw[addr:addr+16];row=bytearray([len(part),addr>>8,addr&255,0])+part
  lines.append(':'+row.hex().upper()+f'{-sum(row)&255:02X}')
 lines.append(':00000001FF')
 (wd/'tinylpc.hex').write_text('\n'.join(lines)+'\n')
 info=dict(phrase=phrase,flavor=flavor,code=code,frames=n,keys=int(mask.sum()),speech=len(packed),flash=len(fw),dir=str(wd))
 (wd/'build.json').write_text(json.dumps(info,indent=2))
 return info

if __name__=='__main__':
 infos=[]
 for p in DATA:
  for alg in ['keyframe','adaptive']:
   try:
    x=compile_matrix(p,alg);print(x);infos.append(x)
   except Exception as e:print('ERR',p,alg,e)
 (R/'new_matrix'/'status.json').write_text(json.dumps(infos,indent=2))
