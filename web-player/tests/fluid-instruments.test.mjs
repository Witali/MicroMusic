import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { AVRCore } from '../lib/avr-core.js';
const folder=new URL('../../ATtiny13A/Music/variants/fluid-instruments/',import.meta.url);
const read=name=>readFileSync(new URL(name,folder));
const report=JSON.parse(read('fit-report.json'));
function initialized(){
  const c=new AVRCore(read('synth.bin'),read('eeprom.bin'));
  while(c.irqCount<30||c.inIRQ)c.step();
  c.r[1]=0;return c;
}
function tick(c){
  c.r[15]=c.r[23]=255;c.r[22]=255;
  const goal=c.irqCount+1;
  while(c.irqCount<goal||c.inIRQ)c.step();
}

test('all tonal tables fit softer FluidR3 targets across the measured note grid',()=>{
  const waves=JSON.parse(read('waveforms.json')),ep=read('eeprom.bin');
  assert.equal(Object.keys(waves).length,8);assert.equal(ep.length,64);
  for(const [index,[name,wave]]of Object.entries(waves).entries()){
    const actual=Array.from(ep.subarray(index*8,index*8+8)).flatMap(b=>[(b&15)-8,(b>>4)-8]);
    assert.deepEqual(actual,wave);assert.equal(wave.reduce((a,b)=>a+b),0);
    const grid=report.waves[name].gridErrors;
    assert.ok(grid.length>=10);
    assert.ok(grid.reduce((s,n)=>s+n.after,0)<grid.reduce((s,n)=>s+n.before,0),name);
    assert.ok(report.waves[name].upperHarmonicPowerAfter<report.waves[name].upperHarmonicPowerBefore,name+' softened');
    if(name.endsWith('sustain'))assert.ok(report.waves[name].attackCorrelation>0,name+' crossfade');
  }
  const previous=new URL('../fluid-violin/',folder);
  for(const name of ['score.inc','score.json','config.inc'])assert.deepEqual(read(name),readFileSync(new URL(name,previous)));
});

test('real AVR piano and guitar decay follows the fitted curve at every tick phase',()=>{
  const {highThreshold,lowThreshold,instruments}=report.envelopes;
  for(let phase=0;phase<32;phase++){
    const c=initialized();c.r[24]=phase;c.r[19]=c.r[20]=143;
    const levels={piano:15,guitar:15};
    for(let t=1;t<=256;t++){
      tick(c);
      for(const [name,reg]of [['piano',19],['guitar',20]]){
        let mask=instruments[name].mask;
        if(levels[name]<highThreshold)mask=mask*2+1;
        if(levels[name]<lowThreshold)mask=mask*2+1;
        if(levels[name]&&((phase+t)&mask)===0)levels[name]--;
        assert.equal(c.r[reg],128+levels[name],`${name}, phase ${phase}, tick ${t}`);
      }
    }
    assert.equal(c.lost,0);assert.ok(c.maxIRQ<512);
  }
  for(const data of Object.values(instruments))assert.ok(data.rmsError<data.originalRmsError);
});

test('independent note-off gives piano a faster release than nylon guitar, including level one',()=>{
  for(let level=1;level<=15;level++){
    const c=initialized();c.r[19]=c.r[20]=level;
    for(let t=1;t<=16;t++){
      tick(c);assert.equal(c.r[19],Math.max(0,level-2*t));assert.equal(c.r[20],Math.max(0,level-t));
    }
  }
});

test('new envelope helpers retain the entire score and all note-off tokens within the IRQ budget',()=>{
  const c=initialized(),sections=new Set(),tokens=new Set();
  for(let n=0;n<950;n++){
    c.r[15]=c.r[23]=255;c.r[22]=1;
    const goal=c.irqCount+4;
    while(c.irqCount<goal||c.inIRQ){
      if(c.pc===0xc0/2)tokens.add(c.rom[c.r[30]|c.r[31]<<8]);
      c.step();
    }
    sections.add(c.r[28]);
  }
  assert.equal(c.lost,0);assert.ok(c.maxIRQ<512,`${c.maxIRQ} cycles`);
  for(let n=0;n<15;n++)assert.ok(sections.has(n));
  for(const token of [0xf2,0xf4,0xf6,0xf8,0xff])assert.ok(tokens.has(token));
});
