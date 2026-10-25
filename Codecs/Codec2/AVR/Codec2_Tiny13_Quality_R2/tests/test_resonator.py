#!/usr/bin/env python3
"""Run original AVR assembly at instruction level; compare independent Python
fixed-point synthesizer. This is not an electrical or hardware AVR simulator.
"""
from pathlib import Path
import sys,math,random,wave,struct,statistics,hashlib,re,time
from codec2_test_common import fields,parse_asm
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'/'codec2tiny_resonator.S'
GAIN_TAB = [0,0,8,8,8,9,9,9,9,9,9,9,9,9,9,9,17,17,17,25,25,33,33,41,50,58,66,83,99,116,140,149]
ROM_TAB=[(min(250,round(256*math.sin(math.pi*100*j/8000)))+2)//4 for j in range(31)]

def s8(x):return x-256 if x&128 else x
def truncdiv(a,b):return a//b if a>=0 else -((-a)//b)

def reference_decoder(frames,write_wave=None,debug=False):
    velocity=[0,0,0];y=[0,0,0];phase=0;noise=0xa5;index=0;prev_e=0;curr_k=[0]*3
    pcm=[];frame_output=[];state_traces=[]
    for f in frames:
      a,b,p,e,l=fields(f);pstep=410+22*p+(p>>2)+(p>>3)
      pos=0;ks=[]
      for i in range(6):
        z=l[i]
        delta = z+1 if i not in (3,4,5) or z<8 else (2*z-6)
        pos=(pos+delta)&255
        if i%2==0: prev=pos
        else:
          desired=(((prev+pos)&255)|(((prev+pos)>>8)<<8))>>1
          # ror after 8-bit add with carry => true integer average of 9-bit sum.
          ks.append(ROM_TAB[min(30,desired>>2)])
      for j in range(160):
        if (j&7)==0:
          curr_k=[z+min(1,max(-1,tar-z)) for z,tar in zip(curr_k,ks)]
        voice=a if j<80 else b
        t=phase+pstep;pulse=t>65535;phase=t&65535
        gain=(GAIN_TAB[(prev_e+e)//2] if j<80 else GAIN_TAB[e])
        gv=gain>>3;gn=gain&7
        if voice:
          excite=gv if pulse else 0
        else:
          noise^=(noise<<3)&255;noise&=255
          noise^=(noise>>5);noise&=255
          noise^=(noise<<1)&255;noise&=255
          excite=gn
          if noise&128:excite=-excite
        out=0
        for h in range(3):
          old_v=velocity[h]
          v=(old_v - (truncdiv(curr_k[h]*s8(y[h]),32)))&255
          leak=((s8(v)+15)//16) if s8(v)>0 else (s8(v)//16)
          v=(v-leak+excite)&255
          new_y=(y[h]+(truncdiv(curr_k[h]*s8(v),32)))&255
          velocity[h]=v;y[h]=new_y
          out=(out+new_y)&255
        out=max(-64,min(63,s8(out)))
        out=((out<<1)+128)&255
        pcm.append(out)
        if debug:state_traces.append((tuple(velocity),tuple(y),tuple(curr_k),noise,gain,phase,excite,out))
      frame_output.append(pcm[-160:])
      prev_e=e
    if write_wave:
      with wave.open(str(write_wave),'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000)
        f.writeframes(struct.pack('<'+'h'*len(pcm), *((int(x)-128)*256 for x in pcm)))
    return (pcm,state_traces) if debug else pcm

class AVR:
 def __init__(self, inst, labels, sym):
    self.inst=inst;self.labels=labels;self.sym=sym
    self.r=[0]*32;self.mem=bytearray(256)
    self.c=self.z=0;self.total=0;self.max_stack=0
    self.qmem={}
    self.isr_stack=[]
    self.rom=bytearray(4096)
    self.coeff_addr=sum(4 if op in ('sts','lds') else 2 for op,_,_ in inst)
    self.rom[self.coeff_addr:self.coeff_addr+31]=bytes(ROM_TAB)
    self.gain_addr=self.coeff_addr+31
    self.rom[self.gain_addr:self.gain_addr+32]=bytes(GAIN_TAB)
 def eval(self,e):
    e=e.strip()
    if e in self.qmem:return self.qmem[e]
    for name,val in self.sym.items():e=re.sub(r'\b'+name+r'\b',str(val),e)
    e=e.replace('lo8(coeff_table)',str(self.coeff_addr&255)).replace('hi8(coeff_table)',str(self.coeff_addr>>8)).replace('lo8(gain_table)',str(self.gain_addr&255)).replace('hi8(gain_table)',str(self.gain_addr>>8)).replace('lo8(410)','154').replace('hi8(410)','1')
    assert re.fullmatch(r'[0-9a-fxA-F+\- ()]+',e),repr(e)
    val=eval(e,{'__builtins__':{}},{})
    self.qmem[e]=val;return val
 def run(self,label,max_steps=20000):
    pc=self.labels[label];call=[];total=0;steps=0;r=self.r
    while True:
      steps+=1
      if steps>max_steps:raise AssertionError(('runaway',label,pc))
      op,aa,addr=self.inst[pc];pc+=1
      x=int(aa[0][1:]) if aa and re.fullmatch(r'r\d+',aa[0]) else None
      cycles=1
      if op in ('ldi','subi','cpi','andi'):
        val=self.eval(aa[1])&255
        if op=='ldi':r[x]=val
        elif op=='andi':r[x]=r[x]&val;self.z=int(r[x]==0)
        else:
          old=r[x];new=(old-val)&255
          self.z=int(new==0);self.c=int(old<val)
          if op=='subi':r[x]=new
      elif op in ('mov','add','adc','sub','cp','and','or','eor'):
        v=r[int(aa[1][1:])];old=r[x]
        if op=='mov':r[x]=v
        elif op in ('add','adc'):
          n=old+v+(self.c if op=='adc' else 0);r[x]=n&255;self.c=int(n>255);self.z=int(r[x]==0)
        elif op in ('sub','cp'):
          n=(old-v)&255;self.c=int(old<v);self.z=int(n==0)
          if op=='sub':r[x]=n
        else:
          r[x]={'and':old&v,'or':old|v,'eor':old^v}[op];self.z=int(r[x]==0)
      elif op in ('clr','lsl','lsr','rol','ror','asr','inc','dec','tst','neg'):
        old=r[x]
        if op=='clr':r[x]=0
        elif op=='lsl':self.c=bool(old&128);r[x]=(old<<1)&255
        elif op=='lsr':self.c=bool(old&1);r[x]=old>>1
        elif op=='rol':oldc=self.c;self.c=bool(old&128);r[x]=((old<<1)|oldc)&255
        elif op=='ror':oldc=self.c;self.c=bool(old&1);r[x]=((old>>1)|(oldc<<7))&255
        elif op=='asr':self.c=bool(old&1);r[x]=(old>>1)|(old&128)
        elif op=='inc':r[x]=(old+1)&255
        elif op=='dec':r[x]=(old-1)&255
        elif op=='neg':r[x]=(-old)&255;self.c=bool(old)
        self.z=int(r[x]==0)
      elif op in ('lds','sts'):
        if op=='lds':r[x]=self.mem[self.eval(aa[1])]
        else:self.mem[self.eval(aa[0])]=r[int(aa[1][1:])]
        cycles=2
      elif op=='ld':
        rd=x;ptr=aa[1];pre=ptr.startswith('-');post=ptr.endswith('+');base=ptr.strip('-+').upper();i={'X':26,'Y':28,'Z':30}[base]
        addr=(r[i]|(r[i+1]<<8))
        if pre:addr=(addr-1)&65535
        assert addr<256,(base,addr)
        r[rd]=self.mem[addr]
        if pre or post:
          if post:addr=(addr+1)&65535
          r[i]=addr&255;r[i+1]=addr>>8
        cycles=2
      elif op=='st':
        ptr=aa[0];pre=ptr.startswith('-');post=ptr.endswith('+');base=ptr.strip('-+').upper();i={'X':26,'Y':28,'Z':30}[base]
        addr=(r[i]|(r[i+1]<<8))
        if pre:addr=(addr-1)&65535
        assert addr<256,(base,addr)
        self.mem[addr]=r[int(aa[1][1:])]
        if pre or post:
          if post:addr=(addr+1)&65535
          r[i]=addr&255;r[i+1]=addr>>8
        cycles=2
      elif op=='push':
        self.isr_stack.append(r[x]);cycles=2
      elif op=='pop':
        r[x]=self.isr_stack.pop();cycles=2
      elif op=='in':
        io=self.eval(aa[1]);r[x]=((self.z<<1)|self.c) if io==0x3f else self.mem[io+0x20]
      elif op=='out':
        io=self.eval(aa[0]);v=r[int(aa[1][1:])]
        if io==0x3f:self.z=bool(v&2);self.c=bool(v&1)
        else:self.mem[io+0x20]=v
      elif op=='sei':
        pass
      elif op=='reti':
        total+=4;self.total+=total;return total
      elif op=='lpm':
        i=r[30]|r[31]<<8
        r[x]=self.rom[i];cycles=3
      elif op=='adiw':
        i=int(aa[0][1:]);full=(r[i]|r[i+1]<<8)+self.eval(aa[1]);n=full&65535
        r[i]=n&255;r[i+1]=n>>8;self.z=int(n==0);self.c=int(full>65535);cycles=2
      elif op in ('breq','brne','brlo','brcs','brcc','brsh'):
        yes={'breq':self.z==1,'brne':self.z==0,'brlo':self.c==1,'brcs':self.c==1,'brcc':self.c==0,'brsh':self.c==0}[op]
        if yes:pc=self.labels[aa[0]];cycles=2
      elif op=='rjmp':pc=self.labels[aa[0]];cycles=2
      elif op=='rcall':call.append(pc);pc=self.labels[aa[0]];cycles=3;self.max_stack=max(self.max_stack,2*len(call))
      elif op=='ret':
        cycles=4
        if call:pc=call.pop()
        else:total+=cycles;self.total+=total;return total
      elif op in ('sbrc','sbrs'):
        b=(r[int(aa[0][1:])]& (1<<self.eval(aa[1])))!=0
        skip=(not b) if op=='sbrc' else b
        if skip:cycles=3 if self.inst[pc][0] in ('lds','sts') else 2;pc+=1
      else:raise AssertionError(('unexpected AVR opcode',op,aa,addr))
      total+=cycles


def inspect():
    # Parse symbolically the exact source that LLVM compiled; ROM data from assembly.
    inst,labels,sym=parse_asm(SRC)
    sim=AVR(inst,labels,sym)
    assert sim.coeff_addr>0
    # Microchip AVR instruction manual: CLR/EOR does not modify Carry.
    # This particular coefficient pointer crosses a 256-byte Flash boundary.
    sim.c=1
    sim.r[20]=120  # /4 == LUT index 30
    sim.run('formant_coeff')
    assert sim.r[20]==ROM_TAB[30], 'Carry lost in Flash table lookup'
    sim.c=0
    init_cycles=sim.run('codec2tiny_init')
    print('CORE',len(inst),'instructions, init',init_cycles,'cycles, formant LUT',ROM_TAB)
    streams=[]
    for name in ('speech.c2zx','codec2_3200_8byte_frames.bin'):
      data=(ROOT/'tests'/name).read_bytes()
      fs=[data[i:i+8] for i in range(0,len(data),8)]
      streams.append((name,fs))
    dc=[];sc=[];mismatches=[];max_sample=None;begin=time.monotonic();testsum=0
    # Entire codec stream with exact assembly state, plus independent synthesizer.
    for name,frames in streams:
      all_frames=frames
      frames=frames[:24]  # 24 consecutive frames per stream in full AVR interpreter
      sim=AVR(inst,labels,sym);sim.run('codec2tiny_init')
      expect=reference_decoder(frames, ROOT/'audio'/(name+'.resonator_ref.wav'))
      reference_decoder(all_frames, ROOT/'audio'/(name+'.resonator_full.wav'))
      pcm=[]
      for i,fr in enumerate(frames):
        sim.mem[0x60:0x68]=fr
        dc.append(sim.run('codec2tiny_decode_frame'))
        _,_,p,e,ls=fields(fr)
        assert sim.mem[0x6a]==p and sim.mem[0x6b]==GAIN_TAB[e]
        phase_step=sim.mem[0x6c]+(sim.mem[0x6d]<<8)
        assert phase_step == 410+22*p+(p>>2)+(p>>3)
        pp=0;cs=[]
        for h in range(6):
          ll=ls[h];diff=ll+1 if h not in (3,4,5) or ll<8 else 2*ll-6
          pp=(pp+diff)&255
          if h%2==0:prev=pp
          else:cs.append(ROM_TAB[min(30,((prev+pp)>>1)>>2)])
        got=list(sim.mem[0x80:0x83]);assert got==cs,(name,i,'targets',got,cs)
        for j in range(160):
          cy=sim.run('codec2tiny_sample');sc.append(cy)
          out=sim.r[16];idx=i*160+j
          if out!=expect[idx] and len(mismatches)<20:mismatches.append((name,i,j,out,expect[idx]))
          pcm.append(out)
      testsum+=len(pcm)
      with wave.open(str(ROOT/'audio'/(name+'.resonator_avr.wav')),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
        w.writeframes(struct.pack('<'+'h'*len(pcm),*((int(v)-128)*256 for v in pcm)))
      print(f'{name}: {len(frames)} frames {len(pcm)} PCM samples, mismatches {len(mismatches)}')
    assert not mismatches,mismatches[:8]
    print(f'FULL {testsum} PCM samples exactly match independent fixed point model.')
    print(f'DECODE cycle min/mean/max: {min(dc)} / {statistics.mean(dc):.1f} / {max(dc)}')
    print(f'SAMPLE cycle min/mean/max: {min(sc)} / {statistics.mean(sc):.1f} / {max(sc)}')
    print(f'Worst demonstrable per-sample {max(sc)}, worst frame upper bound {max(dc)+160*max(sc)}, 9.6MHz budget 192000')
    print(f'Intrinsic call depth {sim.max_stack} bytes; elapsed {time.monotonic()-begin:.1f}s')
    assert max(sc)<1000,'Insufficient time per sample with ISR'
    run_timer0_test(max(sc))
    (ROOT/'tests'/'measured_cycles.txt').write_text(f'Frames={len(dc)}\nSamples={len(sc)}\nDecodeMax={max(dc)}\nSampleMean={statistics.mean(sc):.2f}\nSampleMax={max(sc)}\nFrameBound={max(dc)+160*max(sc)}\n')

def run_timer0_test(max_sample_cycles):
    # Build a source-level program by concatenating assembled sources (same as CPP include).
    source=(ROOT/'src'/'tiny13_pwm_resonator_demo.S').read_text()
    core=SRC.read_text()
    # Ignore demo data directive; no ROM is accessed in the ISR itself.
    import tempfile
    combined=source.replace('#include "codec2tiny_resonator.S"',core)
    with tempfile.NamedTemporaryFile('w+',suffix='.S') as q:
      q.write(combined);q.flush()
      inst,labels,sym=parse_asm(Path(q.name))
    sim=AVR(inst,labels,sym)
    sim.mem[0x7d]=0;sim.mem[0x7c]=1;sim.mem[0x7b]=132
    updates=0;cycles=[];input0=sim.r.copy()
    for i in range(750):
      sim.mem[0x7c]=1  # producer ready for each newly scheduled output
      cycle=sim.run('pwm_ovf_irq');cycles.append(cycle)
      assert sim.r==input0,'ISR does not restore all touched registers'
      assert not sim.isr_stack
      # OCR0B physical I/O address 0x29 maps to memory-mapped address 0x49.
      if sim.mem[0x7c]==0:updates+=1
    assert updates==160,updates
    import collections
    stat=collections.Counter(cycles)
    # During one output sample, ISR normally executes 4 or 5 times.
    over=max_sample_cycles + 5*max(cycles)+20
    print('TIMER0_ISR',len(cycles),'interrupts =>',updates,'samples, min/mean/max',min(cycles),round(statistics.mean(cycles),2),max(cycles),'cycles, sample+5 ISR+20 budget=',over,'vs 1200')
    assert over<1200,f'No safe 8kHz budget with ISR: {over}'
    (ROOT/'tests'/'isr_cycles.txt').write_text(f'Overflows=750\nSamples=160\nISRMin={min(cycles)}\nISRMean={statistics.mean(cycles):.3f}\nISRMax={max(cycles)}\nSampleWorstPlus5ISRAnd20={over}\n')

if __name__=='__main__':inspect()
