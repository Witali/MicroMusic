// Execute the real assembly sections in independently bounded 1 KiB fixtures.
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {AVRCore as JS} from '../web-player/lib/avr-reference.js';
import {AVRCore as Wasm} from '../web-player/lib/avr-core.js';
const manifest=JSON.parse(readFileSync(process.argv[2]));
const signed=x=>x&128?x-256:x;
const signed16=x=>x&32768?x-65536:x;
const hash=x=>createHash('sha256').update(x).digest('hex');
const results=[];
assert.equal(hash(readFileSync(manifest.source,'utf8').replaceAll('\r\n','\n')),manifest.source_sha256);
for(const [engine,Core] of [['JS',JS],['WASM',Wasm]]) {
  let calls=0,maxCycles=0,minSP=159;
  const invoke=(cpu,symbols,label)=>{
    cpu.pc=symbols[label]/2;cpu.sp=159;cpu.sreg=0;cpu.cyc=0;cpu.pushPC(0);
    let steps=0;
    do {cpu.step();if(++steps>2000)throw new Error('Kernel did not return: '+label);}while(cpu.pc!==0);
    assert.equal(cpu.sp,159);assert.equal(cpu.r[0],0);
    calls++;maxCycles=Math.max(maxCycles,cpu.cyc);minSP=Math.min(minSP,cpu.minSP);
  };
  for(const spec of manifest.core) {
    const image=readFileSync(spec.image);assert.equal(image.length,spec.bytes);assert.ok(image.length<=1024);
    assert.equal(hash(image),spec.image_sha256);
    const cpu=new Core(image,null,{fastIdle:false,fastBlocks:false}),s=spec.symbols;
    if(spec.shift===7&&!spec.specialized) {
      for(const a of [-32768,-32640,-2176,-1024,-255,-128,-15,-1,0,1,15,127,255,2176,32640,32767])
        for(let b=0;b<256;b++) {
          cpu.r[18]=a;cpu.r[19]=a>>8;cpu.r[22]=b;invoke(cpu,s,'multiply');
          assert.equal(cpu.r[24]|cpu.r[25]<<8,(a*b)&65535,`multiply ${a}*${b}`);
        }
      for(const [header,residual,phase,history,expected] of manifest.render_cases) {
        cpu.data.fill(0,0x68,0x78);if(history)cpu.data.set(history.map(x=>x&255),0x68);
        cpu.r[16]=header;cpu.r[17]=residual;cpu.r[10]=phase;cpu.r[11]=phase>>8;
        invoke(cpu,s,'render');
        assert.equal(signed(cpu.r[24]),expected,`render ${header}/${residual}, phase ${phase}`);
      }
      for(const [packed,history,expected] of manifest.fir_cases) {
        cpu.rom.set(packed,s.noise_data);cpu.data.set([...history.map(x=>x&255),0],0x68);cpu.r[17]=1;
        invoke(cpu,s,'colored_noise');
        assert.equal(signed16(cpu.r[24]|cpu.r[25]<<8),expected,'signed FIR');
      }
      for(let value=0;value<65536;value++) {
        cpu.r[24]=value;cpu.r[25]=value>>8;invoke(cpu,s,'saturate');
        assert.equal(signed(cpu.r[24]),Math.max(-128,Math.min(127,signed16(value))));
      }
      for(const first of [-128,-127,-1,0,1,126,127])for(const second of [-128,-127,-1,0,1,126,127])
        for(let blend=0;blend<64;blend++) {
          cpu.r[20]=first;cpu.r[24]=second;cpu.r[1]=blend;invoke(cpu,s,'blend_step');
          assert.equal(signed(cpu.r[24]),first+Math.floor(((second-first)*blend+32)/64),'frame blend');
        }
      for(let pitch=0;pitch<256;pitch++)for(const phase of [0,1,32767,65535]) {
        cpu.r[6]=pitch;cpu.r[10]=phase;cpu.r[11]=phase>>8;invoke(cpu,s,'phase_step');
        assert.equal(cpu.r[10]|cpu.r[11]<<8,(phase+(pitch<<5))&65535,'phase carry');
      }
    }
    if(spec.shift===7) {
      for(const [header,residual,phase,history,expected] of spec.render_cases??[]) {
        cpu.data.fill(0,0x68,0x78);if(history)cpu.data.set(history.map(x=>x&255),0x68);
        cpu.r[16]=header;cpu.r[17]=residual;cpu.r[10]=phase;cpu.r[11]=phase>>8;
        invoke(cpu,s,'render');
        assert.equal(signed(cpu.r[24]),expected,`${spec.name} render ${header}/${residual}, phase ${phase}`);
      }
      for(const seed of [1,0xace1,65535]) {
        cpu.data.fill(0,0x68,0x78);cpu.r[12]=seed;cpu.r[13]=seed>>8;
        let next=seed,history=Array(16).fill(0);
        for(let i=0;i<256;i++) {
          for(let bit=0;bit<8;bit++)next=(next>>>1)^((next&1)?0xb400:0);
          history=spec.features?.HISTORY_LENGTH===2
            ? [((next&255)-128)&255,history[0],...Array(14).fill(0)]
            : [((next&255)-128)&255,...history.slice(0,14),0];
          invoke(cpu,s,'noise_step');
          assert.equal(cpu.r[12]|cpu.r[13]<<8,next,'LFSR');
          assert.deepEqual([...cpu.data.subarray(0x68,0x78)],history,'noise history');
        }
      }
    }
    for(const [state,input,expected,final] of manifest.dc_cases[String(spec.shift)]) {
      cpu.data[0x61]=state;cpu.data[0x62]=state>>8;cpu.r[24]=input;invoke(cpu,s,'dc_step');
      assert.equal(signed(cpu.r[24]),expected,'DC output');
      assert.equal(signed16(cpu.data[0x61]|cpu.data[0x62]<<8),final,'DC accumulator');
    }
  }
  let frames=0;
  for(const spec of manifest.reader) {
    const image=readFileSync(spec.image);assert.ok(image.length<=1024);assert.equal(hash(image),spec.image_sha256);
    const cpu=new Core(image,null,{fastIdle:false,fastBlocks:false}),s=spec.symbols;
    cpu.r[26]=s.field_data;cpu.r[27]=s.field_data>>8;cpu.data[0x60]=1;
    for(const [pitch,header,residual] of spec.frames) {
      invoke(cpu,s,'read_frame');frames++;
      assert.equal(cpu.r[14],pitch,`pitch ${spec.name}`);
      assert.equal((cpu.r[4]>>4)&7,(header>>4)&7,'gain');
      if(header&0x70)assert.equal(cpu.r[4],header,'active base');
      assert.equal(cpu.r[5]&15,residual&15,'residual level');
      if(residual&15)assert.equal(cpu.r[5],residual,'active color');
    }
    assert.ok((cpu.r[26]|cpu.r[27]<<8)<=image.length,'bit reader remains inside Flash');
  }
  results.push({engine,calls,frames,maxKernelCycles:maxCycles,minimumSP:minSP});
}
console.log(JSON.stringify({pass:true,sourceSha256:manifest.source_sha256,
  fixtures:[...manifest.core,...manifest.reader].map(({name,bytes,image_sha256})=>({name,bytes,sha256:image_sha256})),
  results,scope:'isolated arithmetic and parser; complete firmware fit and interrupt deadlines unverified'},null,2));
