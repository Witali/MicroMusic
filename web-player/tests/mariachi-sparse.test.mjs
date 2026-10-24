import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

const base=new URL('../../ATtiny13A/Music/variants/cancion-del-mariachi-sparse/',import.meta.url);
const read=name=>readFileSync(new URL(name,base));
const meta=JSON.parse(read('build-report.json')),score=JSON.parse(read('compiled-score.json'));
const arrangement=JSON.parse(read('arrangement.json')),rom=read('synth.bin');
const original=JSON.parse(readFileSync(new URL('../cancion-del-mariachi-polyphonic/compiled-score.json',base)));
const hash=b=>createHash('sha256').update(b).digest('hex');

test('Mariachi sparse: preserves every original lead note and leaves space between backing attacks',()=>{
  assert.deepEqual(arrangement.parts[0],original.parts[0]);
  assert.equal(arrangement.parts[0].groups.reduce((n,g)=>n+g.pitches.length,0),117);
  assert.deepEqual(score.parts,arrangement.parts);
  const groups=arrangement.parts[1].groups;
  assert.equal(groups.length,28);assert.equal(groups.reduce((n,g)=>n+g.pitches.length,0),56);
  for(const [i,g] of groups.entries()){
    assert.equal(g.on%960,0);assert.equal(g.off-g.on,480);
    if(i)assert.ok(g.on-groups[i-1].off>=480,'Each backing attack is followed by a quarter-note rest');
    const source=original.parts[1].groups.find(s=>s.on<=g.on&&g.on<s.off)
      ??original.parts[1].groups.findLast(s=>s.on<=g.on);
    assert.ok(source);assert.ok(g.pitches.every(p=>source.pitches.includes(p)));
  }
  assert.equal(meta.verifiedLosslessScore,false,'Rearranged backing is not claimed to preserve all source notes');
  assert.equal(meta.verifiedCodecRoundTrip,true);assert.equal(meta.playedNotes,173);
  assert.equal(rom.length,868);assert.ok(rom.length<=1024);
});

test('Mariachi sparse: Flash decoder retains all 173 arranged notes and their gates',()=>{
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
      const on=end+160*rom[meta.labels.song_gaps+((packed>>4)&7)];end=on+160*(packed&15);
      const pitches=[],shape=meta.labels.song_shapes+rom[address];
      for(let voice=0;voice<(part?6:2);voice++){
        const step=rom.readUInt16LE(shape+2*voice);if(!step)continue;
        pitches.push(Math.round(69+12*Math.log2(step*18750/65536/440)));
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
  assert.equal(report.arrangedNoteGatesVerified,true);assert.equal(report.playedNotes,173);
  assert.deepEqual(report.arrangedNotesByPart,[117,56]);assert.deepEqual(report.chordAttacksByPart,[94,28]);
  assert.equal(report.ringUnderruns+report.lostTimerEvents+report.lostWorkEvents,0);
  assert.ok(report.sramUsedWorstCase<=64&&report.maxRenderElapsedCycles<512);
});

test('Mariachi sparse: catalogue offers new arrangement and keeps the original full score separately',()=>{
  const catalog=JSON.parse(readFileSync(new URL('../firmware.json',import.meta.url)));
  const entry=catalog.entries.find(e=>e.id==='cancion-del-mariachi-sparse');
  const complete=catalog.entries.find(e=>e.id==='cancion-del-mariachi');
  assert.equal(entry.flashSha256,hash(rom));assert.notEqual(entry.flashSha256,complete.flashSha256);
  assert.match(complete.originalPlayer,/cancion-del-mariachi-polyphonic/);
  assert.match(entry.preview,/cancion-del-mariachi-sparse\/preview.wav$/);
});
