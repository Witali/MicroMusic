import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { CPU8080 } from '../../Emulator/core8080.mjs';
import { parseIntelHex } from '../../Emulator/formats.mjs';
import { traceRom } from '../dual-crc-voice/audit.mjs';
import { cReference } from '../voice32/reference.mjs';

const read = name => readFileSync(new URL(name, import.meta.url));
const json = name => JSON.parse(read(name));
const hash = data => createHash('sha256').update(data).digest('hex');
// Separate documented instruction clock, Intel 1975 Rev. B, Appendix B:
// https://whippleway.com/documents/Intel_8080_Programmers_Manual.pdf
const costs = new Map([[0,4],[7,4],[15,4],[0x1d,5],[0x21,10],[0x26,7],[0x31,10],[0x62,5],
  [0x6f,5],[0x76,7],[0x78,5],[0x79,5],[0x7f,5],[0xc1,10],[0xc2,10],[0xc3,10],[0xca,10],
  [0xd1,10],[0xe1,10],[0xe6,7],[0xe9,5],[0xf3,4],[0xf6,7],[0xf9,5],[0xfb,4]]);
function fixedTrace(cpu, stop = () => false) {
  let t=0, level=0, count=0; const pulses=[];
  do {
    const op=cpu.read(cpu.pc), cost=costs.get(op); assert.notEqual(cost,undefined,`clock opcode ${op.toString(16)}`);
    const before=cpu.t; cpu.step(); count++; assert.equal(cpu.t-before,cost);t+=cost;
    const next=op===0xfb?1:op===0xf3?0:level;
    if (next!==level) { if(next)pulses.push({rise:t});else pulses.at(-1).width=t-pulses.at(-1).rise;level=next; }
    assert.ok(count<4000000);
  } while(!cpu.halted&&!stop(cpu));
  return {t,pulses};
}
function crc(data,poly) {
  let value=0;
  for(const byte of data) {value^=byte<<8;for(let bit=0;bit<8;bit++)value=((value<<1)^((value&0x8000)?poly:0))&65535;}
  return value;
}
function transitions(rom,meta,api) {
  const at=label=>parseInt(meta.labels[label],16), page=at('P3_L0')>>8, halt=at('HALT');
  let cases=0;
  for(let phase=0;phase<5;phase++)for(let current=0;current<16;current++) {
    const variants=phase===2?['literal_more','literal_last','repeat_more','repeat_last']:phase>=3?['word','link_literal','link_repeat','eof']:['normal'];
    for(const variant of variants)for(let next=0;next<(variant==='eof'?1:16);next++)for(let flags=0;flags<4;flags++) {
      const memory=new Uint8Array(rom), code=api.storage(next), word=((0x39<<8)|code<<4|7);
      memory.set([word&255,word>>8],0x6000);
      if(variant.startsWith('link')||variant==='eof') {
        memory.set([0x20,0x61],0x6000);
        memory.set(variant==='eof'?[1,0]:[4,page+Number(variant==='link_repeat'),word&255,word>>8],0x6120);
      }
      const cpu=new CPU8080(memory,{pc:at(`P${phase}_L${current}`),sp:0x6000});
      cpu.setpair(0,phase===0?0xa500|code:phase===1?((code<<4|7)<<8)|0xe7:phase===2?((0xa0|code)<<8)|0xe7:word);
      cpu.r[2]=page+Number(variant.startsWith('repeat')||phase===4);
      cpu.r[3]=variant.endsWith('last')?1:2;
      cpu.f={z:flags&1,cy:flags>>1,s:1,p:1,ac:1};
      if(phase>=3)cpu.f.z=+(variant!=='word');
      const nextPhase=phase===2?(variant.startsWith('repeat')?4:3):phase>=3?0:phase+1;
      const target=variant==='eof'?halt:at(`P${nextPhase}_L${next}`);
      const r=fixedTrace(cpu,c=>c.pc===target);
      assert.equal(r.t,164,`${phase}/${current}/${variant}/${next}`);assert.equal(r.pulses.length,2);
      assert.equal(r.pulses[0].rise,4);assert.equal(r.pulses[1].rise,86);
      for(const pulse of r.pulses)assert.equal(pulse.width,4+4*current);
      assert.equal(cpu.memWrites,0);assert.equal(cpu.ioWrites,0);assert.equal(cpu.pc,target);
      if(phase===2){
        assert.equal(cpu.f.z,Number(variant.endsWith('last')),'Z survives phase-2 padding and PCHL');
        assert.equal(cpu.r[3],api.record_step(variant.endsWith('last')?1:2,variant.startsWith('repeat'))>>8);
      }
      if(phase===4&&variant==='word') {assert.equal(cpu.sp,0x6000);assert.equal(cpu.pair(0),word);}
      cases++;
    }
  }
  return cases;
}

export async function auditAll({check=false}={}) {
  const {api,compiler,options}=await cReference({suffix:'-pwm82'}), reports=[];
  for(let byte=0;byte<256;byte++)for(let index=0;index<2;index++) {
    const code=byte>>(4*(1-index))&15;
    assert.equal(api.fast_level(byte,index),code===4?15:code===15?4:code);
  }
  for(const hz of [2000000,2500000,3500000])for(const profile of ['balloon','owl']) {
    const root=`${profile==='owl'?'owl/':''}${hz===3500000?'':`clocks/${hz}/`}`;
    const name=(profile==='owl'?'owl':'dualcrc')+'-voice-pwm82';
    const rom=read(root+name+'.bin'),meta=json(root+name+'.json'),pcm=json(root+'pcm4.json'),source=json(root+'SOURCE.json');
    assert.equal(hash(rom),meta.sha256);assert.equal(rom.length,32768);assert.equal(meta.cpu_hz,hz);
    assert.equal(meta.pulses_per_sample,2);assert.equal(meta.period_t,82);assert.equal(pcm.sample_rate_hz,hz/164);
    assert.deepEqual(parseIntelHex(read(root+name+'.hex').toString()),new Uint8Array(rom));
    assert.equal(hash(read(root+source.canonical_wav)),source.canonical_sha256);
    assert.equal(source.clipped_source_samples,0);assert.ok(Math.abs(source.source_duration_error_seconds)<.0005);
    const canonical=Buffer.from(pcm.packed_hex,'hex'),expanded=[];
    for(const part of meta.segments) {
      assert.equal(rom[part.header],(part.words+1)&255);assert.equal(rom[part.header+1],(parseInt(meta.labels[part.repeat?'P4_L0':'P3_L0'],16)>>8));
      assert.equal(rom.readUInt16LE(part.link),part.target);assert.ok(part.words>=1&&part.words<=255);
      let remaining=api.record_count(rom[part.header]);assert.equal(remaining,part.words);
      for(let word=0;word<part.words;word++){
        const step=api.record_step(remaining,+part.repeat);remaining=step>>8;
        assert.equal(remaining,part.words-word-1);
        assert.equal(step&255,remaining?(part.repeat?0:1):2);
      }
      const data=rom.subarray(part.data,part.data+part.data_bytes);
      expanded.push(part.repeat?Buffer.concat(Array(part.words).fill(data)):data);
    }
    const encoded=Buffer.concat(expanded);assert.equal(encoded.length,canonical.length);
    for(let i=0;i<canonical.length;i++)for(let n=0;n<2;n++)assert.equal(api.fast_level(encoded[i],n),api.nibble(canonical[i],n));
    assert.equal(meta.stream_bytes,meta.segments.reduce((n,s)=>n+4+s.data_bytes,2));
    assert.ok(meta.stream_bytes<meta.packed_bytes,'lossless compression saves ROM');
    const {result,voice,pulses}=traceRom(rom,meta,{maxInstructions:8000000});
    assert.ok(result.halted);assert.equal(result.writes,0);assert.equal(voice.length,pcm.sample_count*2);
    assert.deepEqual(result.voice.periods_t,{82:voice.length-1});
    for(const [i,pulse] of voice.entries()) {
      const sample=i>>1,q=api.nibble(canonical[sample>>1],sample&1);
      assert.equal(pulse.width,api.width(q));assert.equal(pulse.rise-voice[0].rise,i*82);
    }
    const independent=new CPU8080(new Uint8Array(rom));
    while(independent.pc!==0x1100&&!independent.halted&&independent.count<2500000)independent.step();
    assert.equal(independent.pc,0x1100);
    const grid=fixedTrace(independent);assert.equal(grid.pulses.length,voice.length);
    for(const [i,pulse] of grid.pulses.entries()) {assert.equal(pulse.rise-grid.pulses[0].rise,i*82);assert.equal(pulse.width,voice[i].width);}
    const oldRoot=`../voice32/${root}`,oldName=profile==='owl'?'owl-voice32':'dualcrc-voice32';
    const baseline=traceRom(read(oldRoot+oldName+'.bin'),json(oldRoot+oldName+'.json')).result;
    assert.deepEqual(result.tones,baseline.tones);assert.deepEqual(result.ramp,baseline.ramp);
    if(profile==='owl'){assert.equal(pulses.length,voice.length);assert.equal(voice[0].rise,86);}
    const faults=[];
    if(profile==='balloon')for(let bank=0;bank<8;bank++) {
      const block=rom.subarray(bank*4096,(bank+1)*4096);assert.equal(crc(block,7),0);assert.equal(crc(block,9),0);
      const bad=new Uint8Array(rom);bad[bank*4096+0x900]^=1;
      const failed=traceRom(bad,meta).result;assert.ok(failed.halted);assert.equal(failed.pc,0xf86);assert.equal(failed.voice.samples,0);
      faults.push(bank);
    }
    const cases=transitions(rom,meta,api);
    const report={name,profile,cpu_hz:hz,sha256:meta.sha256,period_t:82,carrier_hz:hz/82,
      pulses_per_sample:2,sample_rate_hz:hz/164,samples:pcm.sample_count,pulses:voice.length,
      maximum_grid_error_t:0,maximum_width_error_t:0,width_step_t:4,lossless_pcm_storage:true,exact_c_reference:true,
      independent_clock_instructions:true,level_and_branch_cases:cases,z_live_across_phase_2_checked:true,
      original_packed_bytes:canonical.length,stream_bytes:meta.stream_bytes,free_voice_region_bytes:meta.free_voice_region_bytes,
      source_duration_error_seconds:source.source_duration_error_seconds,quantization_snr_db:source.quantization_snr_db,
      t_states:result.t_states,instructions:result.instructions,first_pwm_rise_t:voice[0].rise,
      halted:true,writes:0,crc_fault_banks:faults,diagnostic_beeps:result.tones.length,
      hardware_tested:false,active_interrupts_supported:false,
      reference:{compiler:compiler.split(/[\\/]/).at(-1),options,target:'WASM portable C99, not a cycle-timed 8080 C build'}};
    const target=new URL(root+'AUDIT.json',import.meta.url);
    if(check)assert.deepEqual(report,JSON.parse(readFileSync(target)));else writeFileSync(target,JSON.stringify(report,null,2)+'\n');
    reports.push(report);console.log(JSON.stringify({profile,hz,pulses:voice.length,cases,grid_error_t:0,stream_bytes:meta.stream_bytes}));
  }
  return reports;
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url))await auditAll({check:process.argv.includes('--check')});
