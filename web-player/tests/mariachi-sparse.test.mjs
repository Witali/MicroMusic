import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

const base=new URL('../../ATtiny13A/Music/variants/cancion-del-mariachi-sparse/',import.meta.url);
const read=name=>readFileSync(new URL(name,base));
const meta=JSON.parse(read('build-report.json')),score=JSON.parse(read('compiled-score.json'));
const arrangement=JSON.parse(read('arrangement.json')),rom=read('synth.bin'),eeprom=read('eeprom.bin');
const original=JSON.parse(readFileSync(new URL('../cancion-del-mariachi-polyphonic/compiled-score.json',base)));
const hash=b=>createHash('sha256').update(b).digest('hex');
const source=JSON.parse(readFileSync(new URL('../../reference/cancion-del-mariachi/source-events.json',base)));
function sourceGroups(part){
  const active=new Map(),notes=[];let order=0;
  for(const e of source.tracks[part].events){
    if(e.type!=='noteOn'&&e.type!=='noteOff')continue;
    const key=`${e.channel}:${e.note}`;
    if(e.type==='noteOn'&&e.velocity){const q=active.get(key)||[];q.push({...e,order:order++});active.set(key,q);}
    else if(active.get(key)?.length){
      const on=active.get(key).shift();
      if(on.tick>=58*480&&on.tick<arrangement.lastTick)
        notes.push({on:on.tick-58*480,off:e.tick-58*480,pitch:on.note,order:on.order});
    }
  }
  const groups=[];
  for(const n of notes.sort((a,b)=>a.on-b.on||a.order-b.order)){
    let g=groups.at(-1);if(!g||g.on!==n.on){g={on:n.on,off:n.off,velocity:80,pitches:[]};groups.push(g);}
    assert.equal(g.off,n.off);g.pitches.push(n.pitch);
  }
  return groups;
}

test('Mariachi sparse: preserves every original lead note and leaves space between backing attacks',()=>{
  assert.deepEqual(arrangement.parts[0].groups,sourceGroups(0));
  assert.deepEqual(arrangement.parts[0].groups.slice(0,original.parts[0].groups.length),original.parts[0].groups);
  assert.equal(arrangement.parts[0].groups.reduce((n,g)=>n+g.pitches.length,0),261);
  assert.deepEqual(score.parts,arrangement.parts);
  const groups=arrangement.parts[1].groups;
  assert.equal(groups.length,60);assert.equal(groups.reduce((n,g)=>n+g.pitches.length,0),120);
  const backing=sourceGroups(1);
  for(const [i,g] of groups.entries()){
    assert.equal(g.on%960,0);assert.equal(g.off,Math.min(g.on+480,arrangement.lastTick-58*480));
    if(i)assert.ok(g.on-groups[i-1].off>=480,'Each backing attack is followed by a quarter-note rest');
    const source=backing.find(s=>s.on<=g.on&&g.on<s.off)??backing.findLast(s=>s.on<=g.on);
    assert.ok(source);assert.ok(g.pitches.every(p=>source.pitches.includes(p)));
  }
  assert.equal(meta.verifiedLosslessScore,false,'Rearranged backing is not claimed to preserve all source notes');
  assert.equal(meta.verifiedCodecRoundTrip,true);assert.equal(meta.playedNotes,381);
  assert.equal(rom.length,1024);assert.ok(rom.length<=1024);
});

test('Mariachi sparse: compact Flash decoder retains all 381 arranged notes and their gates',()=>{
  for(let part=0;part<2;part++){
    let end=0,at=meta.labels.song_stream+score.streamOffsets[part];const groups=[];
    function expand(symbol,depth=0){
      assert.ok(depth<=5);
      if(symbol>=meta.labels.BASE_COUNT){
        const address=meta.labels.song_rules+2*(symbol-meta.labels.BASE_COUNT);
        assert.ok(rom[address]<symbol&&rom[address+1]<symbol);
        expand(rom[address],depth+1);expand(rom[address+1],depth+1);return;
      }
      const address=meta.labels.song_bases+symbol*2,packed=rom[address+1];
      const on=end+80*((packed>>2)&62);end=on+80*rom[meta.labels.song_gates+(packed&7)];
      const pitches=[];let shape=meta.labels.song_shapes+rom[address];
      for(let voice=0;;voice++){
        assert.ok(voice<3);const entry=rom[shape++],step=eeprom.readUInt16LE(entry&127);assert.ok(step);
        const pitch=Math.round(69+12*Math.log2(step*18750/65536/440));
        assert.equal(step,Math.round(440*2**((pitch-69)/12)*65536/18750),'DDS pitch precision is unchanged');pitches.push(pitch);
        if(entry&128)break;
      }
      groups.push({on,off:end,pitches,velocity:80});
    }
    while(rom[at]!==255){assert.ok(at<rom.length);expand(rom[at++]);}
    assert.deepEqual(groups,arrangement.parts[part].groups);
  }
});

test('Mariachi sparse: full AVR audit verifies source lead, rearranged backing and memory bounds',()=>{
  const report=JSON.parse(read('verification.json'));
  assert.equal(report.passed,true);assert.equal(report.flashSha256,hash(rom));
  assert.equal(report.eepromSha256,hash(read('eeprom.bin')));
  assert.equal(report.allSourceNoteGatesVerified,false);assert.equal(report.leadSourceNoteGatesVerified,true);
  assert.equal(report.arrangedNoteGatesVerified,true);assert.equal(report.playedNotes,381);
  assert.deepEqual(report.arrangedNotesByPart,[261,120]);assert.equal(report.chordAttacksByPart[1],60);
  assert.ok(Math.abs(report.firstSongSeconds-60.15867)<.00001);
  assert.equal(report.ringUnderruns+report.lostTimerEvents+report.lostWorkEvents,0);
  assert.ok(report.sramUsedWorstCase<=64&&report.maxRenderElapsedCycles<512);
});

test('Mariachi sparse: real PWM and exported WAV use their peak range with a fixed common gain',()=>{
  const report=JSON.parse(read('verification.json')),normalization=meta.outputNormalization;
  assert.equal(normalization.gain,4);assert.equal(normalization.implementation,'constant-shifts');
  assert.equal(normalization.table[-normalization.minimum],128);
  for(let i=0;i<normalization.table.length;i++)
    assert.equal(normalization.table[i],128+4*(i+normalization.minimum));
  assert.deepEqual(report.pwmRange,[0,252]);assert.equal(report.normalizationClippedSamples,0);
  assert.equal(report.normalizationChecks,report.mixChecks);
  const wav=read('preview.wav'),level=JSON.parse(read('preview-level.json'));
  assert.equal(level.flashSha256,hash(rom));assert.equal(level.wavSha256,hash(wav));
  assert.equal(level.normalized,true);assert.equal(level.peakTarget,1);
  let min=32767,max=-32768;for(let n=44;n<wav.length;n+=2){const s=wav.readInt16LE(n);min=Math.min(min,s);max=Math.max(max,s);}
  assert.equal(Math.max(-min,max),32767);assert.equal(wav.readUInt32LE(40)/(48000*2),61);
});

test('Mariachi sparse: retained old kick/hat profiles run independently of all guitar notes',()=>{
  const previous=JSON.parse(readFileSync(new URL('../cancion-del-mariachi/build-report.json',base)));
  const drum=meta.percussionProfile,report=JSON.parse(read('verification.json'));
  for(const role of ['kick','hat'])assert.deepEqual(drum.hits[role],previous.percussionProfile.hits[role]);
  assert.deepEqual(Object.keys(drum.hits),['kick','hat']);assert.equal(drum.attenuationShift,3);
  assert.deepEqual(meta.partVoiceCounts,[3,3]);assert.equal(meta.oscillators,6);
  assert.equal(drum.independentDrumVoices,1);assert.equal(drum.quarterBeatsPerHit,.5);
  assert.equal(report.drumChecks,report.mixChecks);assert.ok(report.drumEnvelopeChecks>4000);
  assert.deepEqual(report.drumAttacksByType,{kick:127,hat:126});assert.equal(report.drumAttacks,253);
  assert.equal(report.drumGeneratorMatchesRetainedKit,true);assert.equal(report.normalizationIncludesDrums,true);
  assert.ok(report.maximumDrumOnsetErrorMs<25);assert.equal(report.phaseStateBytes,24);
  assert.ok(report.maxStackBytes<=9);assert.equal(report.sramUsedWorstCase,56);
});

test('Mariachi sparse: catalogue offers new arrangement and keeps the original full score separately',()=>{
  const catalog=JSON.parse(readFileSync(new URL('../firmware.json',import.meta.url)));
  const entry=catalog.entries.find(e=>e.id==='cancion-del-mariachi-sparse');
  const complete=catalog.entries.find(e=>e.id==='cancion-del-mariachi');
  assert.equal(entry.flashSha256,hash(rom));assert.notEqual(entry.flashSha256,complete.flashSha256);
  assert.match(complete.originalPlayer,/cancion-del-mariachi-polyphonic/);
  assert.match(entry.preview,/cancion-del-mariachi-sparse\/preview.wav$/);
});
