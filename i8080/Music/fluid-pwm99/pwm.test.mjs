import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {CPU8080} from '../../Emulator/core8080.mjs';
import {parseIntelHex} from '../../Emulator/formats.mjs';
import {auditAll,stepClock} from './audit.mjs';
const read=name=>readFileSync(new URL(name,import.meta.url)),json=name=>JSON.parse(read(name));
const source=json('../uniform-pwm/source-score.json');

test('Six99T music ROMs preserve tempo, pitch, FluidR3 banks and proportional carrier/sample rates',()=>{
  for(const hz of [2000000,2500000,3500000])for(const tune of source.tunes){
    const prefix=hz===3500000?'':`clocks/${hz}/`,name=prefix+tune.name+'-fluid-pwm99';
    const meta=json(name+'.json'),rom=read(name+'.bin'),bank=json(prefix+meta.bank_source);
    assert.equal(meta.cpu_hz,hz);assert.equal(meta.period_t,99);assert.equal(meta.carrier_hz,hz/99);
    assert.equal(meta.frame_t,396);assert.equal(meta.pulses_per_frame,4);assert.ok(meta.used_bytes<=32768);
    assert.equal((hz/99)/(hz/108),(hz/396)/(hz/432));
    assert.equal(meta.sha256,createHash('sha256').update(rom).digest('hex'));
    assert.deepEqual(parseIntelHex(read(name+'.hex').toString()),new Uint8Array(rom));
    assert.equal(meta.bank_sha256,createHash('sha256').update(JSON.stringify(sortKeys(bank))).digest('hex'));
    let elapsed=0,frames=0;
    for(const [index,note] of tune.notes.entries()){
      const now=meta.notes[index];elapsed+=note.duration_t;frames+=now.frames;
      assert.ok(Math.abs(frames*396/hz-elapsed/source.cpu_hz)<=198/hz+1e-12);
      for(let channel=0;channel<2;channel++){
        const step=note.steps[channel];if(step===null){assert.equal(now.steps[channel],null);continue;}
        const target=step*source.cpu_hz/(note.duration_t/note.groups)/65536;
        const actual=now.steps[channel]*hz/396/65536;
        assert.ok(Math.abs(actual-target)<=hz/(396*65536*2)+1e-12);
        const cents=1200*Math.log2(actual/target);assert.ok(Math.abs(cents)<1.5);
        assert.ok(Math.abs(cents-now.pitch_error_cents[channel])<1e-9);
        const midi=Math.round(69+12*Math.log2(target/440));
        assert.ok(actual*bank.banks[channel?2:+(midi>=bank.piano_register_split_midi)].harmonics<hz/396/2);
      }
    }
    assert.equal(frames,meta.frames);assert.equal(frames,meta.chunks.reduce((n,c)=>n+c.frames,0));
  }
});
function sortKeys(value){
  if(Array.isArray(value))return value.map(sortKeys);
  if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(key=>[key,sortKeys(value[key])]));
  return value;
}

test('All96 handlers: independent clock, every level, carry/reset, live Z, normal/link/EOF and incoming flags',()=>{
  const meta=json('uniform26-fluid-pwm99.json'),rom=read('uniform26-fluid-pwm99.bin'),bank=json(meta.bank_source);
  const at=(phase,level)=>parseInt(meta.labels[`P${phase}_L${level}`],16);
  const q=Math.max(0,Math.min(15,Math.floor(((bank.banks[0].waves[0][255]+bank.banks[2].waves[0][171]-meta.mix_minimum_sum)*15+(meta.mix_maximum_sum-meta.mix_minimum_sum)/2)/(meta.mix_maximum_sum-meta.mix_minimum_sum))));
  for(let phase=0;phase<6;phase++)for(let level=0;level<16;level++){
    const variants=phase<2?[1,0x7123,0xfeff,0xff00]:phase===2?['normal','record','eof']:[2];
    for(const value of variants)for(let flags=0;flags<4;flags++)for(const count of phase===1?[1,2,255]:[2]){
      const edges=[],bus={level:0,advance(){},edge(v,t){if(v!==this.level){this.level=v;edges.push([t,v]);}}};
      const cpu=new CPU8080(new Uint8Array(rom),{pc:at(phase,level),sp:phase===2?0x9006:0x9000,audio:bus});
      cpu.mem.set([2,meta.first_wave_page,0,0,0,0,value==='eof'?0:2,meta.first_wave_page],0x9000);
      if(phase<2)cpu.mem.set([value&255,value>>8],0x9000);
      cpu.setpair(0,0xfffe);cpu.setpair(1,0xabcd);cpu.setpair(2,(meta.first_wave_page<<8)|2);
      cpu.r[7]=count;cpu.f={z:flags&1,cy:flags>>1,s:1,p:1,ac:1};
      if(phase===2)cpu.f.z=Number(value!=='normal');
      const nextPhase=phase<2?phase+1:phase===2?(value==='normal'?3:value==='record'?4:5):0;
      const target=at(nextPhase,phase===3||phase===4?q:level);let clock=0;
      do{clock+=stepClock(cpu);}while(!cpu.halted&&cpu.pc!==target&&cpu.count<160);
      assert.equal(clock,99,`${phase}/${level}/${value}/${flags}/${count}`);
      assert.equal(cpu.memWrites,0);assert.equal(cpu.ioWrites,0);assert.equal(cpu.inte,0);
      assert.deepEqual(edges,level?[[4,1],[4+4*level,0]]:[]);
      if(phase===5)assert.ok(cpu.halted);else assert.equal(cpu.pc,target);
      if(phase<2)assert.equal(cpu.pair(phase),value===0xff00?0:((phase?0xabcd:0xfffe)+value)&65535);
      if(phase===1){assert.equal(cpu.r[7],count-1);assert.equal(cpu.f.z,Number(count===1));}
      if(phase===2)assert.equal(cpu.sp,value==='normal'?0x9000:0x9008);
    }
  }
});

test('Complete six ROMs: all99T periods and widths equal C through HLT with no RAM or I/O writes',async()=>{
  let slots=0;
  for(const hz of [2000000,2500000,3500000]){
    const report=await auditAll(hz);assert.deepEqual(report,json((hz===3500000?'':`clocks/${hz}/`)+'AUDIT.json'));
    slots+=report.reports.reduce((n,r)=>n+r.pwm_slots,0);
  }
  assert.equal(slots,12179092);
});
