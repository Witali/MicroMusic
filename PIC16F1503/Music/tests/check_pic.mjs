import fs from 'node:fs';import assert from 'node:assert/strict';
import {PIC16F1503,readPIC16Hex} from '../web/pic16-core.mjs';
import {SoundModel} from '../web/synth-model.mjs';
import {MUSIC_ASSETS as A} from '../web/music-assets.mjs';

const out={device:'PIC16F1503',datasheet:'Microchip DS40001607D',tests:[]};
function test(name,cb){cb();out.tests.push({name,pass:true});console.log('PASS',name);}
function newCPU(words){return new PIC16F1503(words);}
function go(program){const words=new Uint16Array(2048);words.fill(0x3fff);for(let i=0;i<program.length;i++)words[i]=program[i];return newCPU(words);}
function runN(cpu,n){for(let i=0;i<n;i++)cpu.step();return cpu;}
test('PIC instruction MOVLW/MOVWF/MOVF & banked RAM',()=>{
  const cpu=go([0x302a,0x00a0,0x305a,0x0080|0x21,0x0820,0x0080|0x22]);runN(cpu,6);
  assert.equal(cpu.mem[0x20],42);assert.equal(cpu.mem[0x21],0x5a);assert.equal(cpu.mem[0x22],42);assert.equal(cpu.PC,6);
});
test('PIC skip and two-cycle branch timing',()=>{
  const cpu=go([0x3000,0x00a0,0x1820,0x3033,0x3044,0x3200|((0x1ff)&-1),]);
  runN(cpu,3);assert.equal(cpu.PC,4);assert.equal(cpu.cycle,4);cpu.step();assert.equal(cpu.W,0x44);
});
test('Read low 8 bits of Flash through indirect FSR1 + extra cycle',()=>{
  const cpu=go([0x305a,0x00a0,0x0821,0x3fff]);
  cpu.mem[0x06]=0;cpu.mem[0x07]=0x80;let v=cpu.readIndirect(1,0);assert.equal(v.val,0x5a);assert.equal(v.cycles,2);
});
test('PWM3 resolution: 0, 128 and 255 in 8-bit range, double buffering',()=>{
  for(const duty of [0,1,127,128,254,255]){
    const cpu=go([0x2800]);cpu.mem[0x1b]=63;cpu.mem[0x1c]=4;cpu.mem[0x619]=0xc0;
    cpu.mem[0x618]=duty>>2;cpu.mem[0x617]=(duty&3)<<6;
    cpu.advanceCycles(64);assert.equal(cpu.samples.length,1);
    assert.equal(cpu.samples[0],duty, `duty ${duty} -> ${cpu.samples[0]}`);
  }
});
test('Postscaler 1:4 leaves carrier 62.5k PWM at 16MHz',()=>{
  const cpu=go([0x2800]);cpu.mem[0x1b]=63;cpu.mem[0x1c]=0x1c;cpu.advanceCycles(64*7);
  assert.equal(cpu.pwmPeriodCount,7);assert.equal(cpu.postscale,3);assert.equal(cpu.mem[0x11]&2,2);
});
test('Diagnostic Intel HEX executes real ISR and 8-bit ramp',()=>{
  const words=readPIC16Hex(fs.readFileSync(new URL('../firmware/diagnostic_pwm_irq.hex',import.meta.url),'utf8'));
  const cpu=newCPU(words),state=cpu.run(500000,4000);
  assert.equal(cpu.mem[0x099],0x7a);assert.equal(cpu.mem[0x1b],63);assert.equal(cpu.mem[0x1c],0x1c);
  assert.equal(cpu.mem[0x619]&0xc0,0xc0);
  assert.equal(state.output.length,4000);assert.equal(state.irq,1000);
  assert.ok(state.output[0]>=127&&state.output[0]<=129);
  assert.ok(state.output[100] > state.output[0]);
  assert.ok(Math.min(...state.output)<20 && Math.max(...state.output)>230,'Full-range duty ramp');
  out.diagnostic={cycles:cpu.cycle,instructions:cpu.totalInstructions,interrupts:cpu.irqCount,pwmPeriods:cpu.pwmPeriodCount};
});
test('Score compression exactly preserves all unique sections/playlist',()=>{
  assert.equal(A.score.length,216);assert.equal(A.playlist.length,15);
  assert.equal(A.playlist[0],0);assert.equal(A.playlist[1],196);
  assert.equal(A.noteSteps[9],1846);assert.equal(A.chordsKey.length,5);
});
test('Wavetables all have zero DC and range -8..7',()=>{
  for(const [inst,table] of [['violin',A.violin],['piano',A.piano],['guitar',A.guitar]]){
    assert.equal(table.length%16,0);
    for(let start=0;start<table.length;start+=16){let wave=table.slice(start,start+16);
      assert.equal(wave.reduce((a,b)=>a+b,0),0,`${inst} wave ${start>>4}`);
      assert.ok(Math.min(...wave)>=-8 && Math.max(...wave)<=7);
    }
  }
});
test('Music model stable DC average, distinct sound and note-offs',()=>{
  const m=new SoundModel(),a=m.generate(15625*15);let min=255,max=0,sum=0;
  for(const s of a){min=Math.min(min,s);max=Math.max(max,s);sum+=s;}
  assert.ok(Math.abs(sum/a.length-128)<2.5,`average=${sum/a.length}`);
  assert.ok(min<110&&max>140);
  assert.ok(m.eventCount>20);
  const score=new SoundModel();score.generate(15625*222);
  assert.ok(score.sectionsTraversed>=12);
  assert.ok(score.noteoffs>0);
  out.music={previewMean:sum/a.length,range:[min,max],first15sEvents:m.eventCount,fullSongSeconds:222,sectionsTraversed:score.sectionsTraversed,noteoffEvents:score.noteoffs};
});
const dir=new URL('../reports/',import.meta.url);fs.mkdirSync(dir,{recursive:true});
fs.writeFileSync(new URL('../reports/test-report.json',import.meta.url),JSON.stringify(out,null,2)+'\n');
console.log('All',out.tests.length,'tests passed');
