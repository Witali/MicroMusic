import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {AVRCore} from '../lib/avr-core.js';

const base=new URL('../../ATtiny13A/Music/variants/cancion-del-mariachi-polyphonic/',import.meta.url);
const read=name=>readFileSync(new URL(name,base));
const rom=read('synth.bin'),ep=read('eeprom.bin'),meta=JSON.parse(read('build-report.json'));
const verification=JSON.parse(read('verification.json')),compiled=JSON.parse(read('compiled-score.json'));
const raw=readFileSync(new URL('../../reference/cancion-del-mariachi/source-events.json',base));
const source=JSON.parse(raw),hash=data=>createHash('sha256').update(data).digest('hex');
const pc=Object.fromEntries(Object.entries(meta.labels).map(([k,v])=>[k,v/2]));

function originalNotes(){
  return source.tracks.flatMap((track,index)=>{
    const active=new Map(),notes=[];let order=0;
    for(const e of track.events){
      if(e.type!=='noteOn'&&e.type!=='noteOff')continue;
      const key=`${e.channel}:${e.note}`;
      if(e.type==='noteOn'&&e.velocity){
        const queue=active.get(key)||[];queue.push({...e,order:order++});active.set(key,queue);
      }else{
        assert.ok(active.get(key)?.length);const on=active.get(key).shift();
        if(on.tick>=58*480&&on.tick<121*480)
          notes.push({order:on.order,record:[index,on.channel,on.tick-58*480,e.tick-58*480,on.note,on.velocity,e.velocity]});
      }
    }
    assert.ok([...active.values()].every(q=>q.length===0));
    return notes.sort((a,b)=>a.record[2]-b.record[2]||a.order-b.order).map(n=>n.record);
  });
}

test('Mariachi polyphonic: actual Flash phrases preserve every source chord, attack and gate',()=>{
  const expected=originalNotes(),actual=[];
  assert.equal(expected.length,1027);
  assert.equal(hash(raw),meta.sourceSha256);
  assert.equal(hash(JSON.stringify(expected)),meta.decodedNotesSha256);
  assert.deepEqual(expected.map(n=>n[0]).reduce((a,t)=>(a[t]++,a),[0,0]),[117,910]);
  assert.ok(expected.every(n=>n[5]===80&&n[6]===64));
  assert.deepEqual(source.tracks.map(t=>t.events.filter(e=>e.type==='programChange').map(e=>e.program)),[[24],[24]]);
  for(let part=0;part<2;part++){
    let at=meta.labels.song_stream+compiled.streamOffsets[part],end=0;
    const expand=(code,depth=0)=>{
      assert.ok(depth<=5);
      if(code>=meta.labels.BASE_COUNT){
        const rule=meta.labels.song_rules+2*(code-meta.labels.BASE_COUNT),a=rom[rule],b=rom[rule+1];
        assert.ok(a<code&&b<code,'Only backward phrase references');expand(a,depth+1);expand(b,depth+1);return;
      }
      const address=meta.labels.song_bases+2*code,shape=meta.labels.song_shapes+rom[address],packed=rom[address+1];
      const gap=rom[meta.labels.song_gaps+((packed>>4)&7)],gate=packed&15,on=end+160*gap;
      end=on+160*gate;assert.ok(gate>0);
      for(let i=0;i<(part?6:2);i++){
        const step=rom.readUInt16LE(shape+2*i);if(!step)continue;
        const pitch=Math.round(69+12*Math.log2(step*18750/65536/440));
        assert.equal(step,Math.round(440*2**((pitch-69)/12)*65536/18750));
        actual.push([part,part?0:2,on,end,pitch,80,64]);
      }
    };
    while(rom[at]!==255){assert.ok(at<rom.length);expand(rom[at++]);}
  }
  assert.deepEqual(actual,expected);
  assert.equal(meta.tableBytes,352);assert.equal(meta.codeBytes,566);assert.equal(rom.length,918);
  assert.equal(compiled.verifiedLossless,true);
});

test('Mariachi polyphonic: retained full-loop audit belongs to these exact images and fits ATtiny13A',()=>{
  assert.equal(verification.passed,true);
  assert.equal(hash(rom),verification.flashSha256);assert.equal(hash(ep),verification.eepromSha256);
  assert.equal(hash(raw),verification.sourceSha256);
  assert.equal(verification.allSourceNotes,1027);assert.equal(verification.allSourceNoteGatesVerified,true);
  assert.deepEqual(verification.chordAttacksByPart,[94,167]);
  assert.equal(verification.oscillators,8);assert.equal(verification.maximumSimultaneousSourceNotes,7);
  assert.ok(verification.flashBytes<=1024&&verification.sramUsedWorstCase<=64);
  assert.equal(verification.sramUsedWorstCase,61);assert.equal(ep.length,64);
  assert.ok(verification.maximumOnsetErrorMs<15&&verification.maximumGateEndErrorMs<15);
  assert.ok(verification.maximumPitchQuantizationErrorCents<2.16);
  assert.equal(verification.lostTimerEvents+verification.lostWorkEvents+verification.ringUnderruns,0);
  assert.ok(verification.minQueuedPwmBytes>0&&verification.maxRenderActiveCycles<512);
  assert.equal(verification.independentPhaseChecks,verification.mixChecks*8);
  assert.equal(verification.mixChecks,verification.pwmPairChecks);assert.ok(verification.mixChecks>580000);
  assert.equal(verification.bothPartsSilentBeforeRestart,true);assert.ok(verification.loopSeconds>31&&verification.loopSeconds<31.2);
});

test('Mariachi polyphonic: AVR plucked envelope agrees at every clock, level and held state',()=>{
  const core=new AVRCore(rom,ep,{fastIdle:false});let checks=0;
  for(let clock=0;clock<256;clock++)for(let held=0;held<=128;held+=128)for(let level=0;level<16;level++){
    const value=held|level,mask=level>=10?1:level>=7?3:7;
    const expected=value-Number(level>0&&(!held||!(clock&mask)));
    core.pc=pc.envelope;core.r[20]=value;core.r[14]=clock;
    while(core.pc!==pc.envelope_return)core.step();
    assert.equal(core.r[20],expected);checks++;
  }
  assert.equal(checks,8192);
});

test('Mariachi polyphonic: AVR signed gain retains all chord tones and rounding at every level',()=>{
  const core=new AVRCore(rom,ep,{fastIdle:false});let checks=0;
  for(let sum=-48;sum<=42;sum++)for(let level=0;level<16;level++){
    core.pc=pc.chord_gain;core.r[21]=sum&255;core.r[25]=level;
    while(core.pc!==pc.gain_return)core.step();
    const value=core.r[17]&128?core.r[17]-256:core.r[17];
    assert.equal(value,Math.floor(sum*level/8)||0);checks++;
  }
  assert.equal(checks,1456);
});

test('Mariachi polyphonic: default song points to all notes and keeps the reduced ensemble for comparison',()=>{
  const catalog=JSON.parse(readFileSync(new URL('../firmware.json',import.meta.url)));
  const current=catalog.entries.find(e=>e.id==='cancion-del-mariachi');
  const old=catalog.entries.find(e=>e.id==='cancion-del-mariachi-ensemble');
  assert.equal(current.flashSha256,hash(rom));assert.equal(current.eepromSha256,hash(ep));
  assert.equal(current.voices,8);assert.equal(current.releaseTailSlots,0);
  assert.deepEqual(Object.values(current.instruments).map(i=>i.gmProgram),[24,24]);
  assert.match(current.originalPlayer,/cancion-del-mariachi-polyphonic\/player.html$/);
  assert.match(current.preview,/cancion-del-mariachi-polyphonic\/preview.wav$/);
  assert.match(old.originalPlayer,/variants\/cancion-del-mariachi\/player.html$/);
  assert.notEqual(current.flashSha256,old.flashSha256);
  const wav=read('preview.wav');assert.equal(wav.toString('ascii',0,4),'RIFF');
  assert.equal(wav.readUInt16LE(22),1);assert.equal(wav.readUInt32LE(24),48000);
  assert.equal(wav.readUInt32LE(40)/(48000*2),30.9);
});
