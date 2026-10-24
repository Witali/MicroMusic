// Compare the shipped AVR arrangement with every original note in the excerpt.
// Original notes are paired independently; the arranger/codec are not imported.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {AVRCore} from '../web-player/lib/avr-core.js';

const root=fileURLToPath(new URL('../',import.meta.url));
const folder=path.join(root,'ATtiny13A/Music/variants/cancion-del-mariachi');
const read=name=>fs.readFileSync(path.join(folder,name));
const score=JSON.parse(read('score.json')),meta=JSON.parse(read('build-report.json'));
const sourceRaw=fs.readFileSync(path.resolve(folder,score.source.file)),source=JSON.parse(sourceRaw);
const rom=read('synth.bin'),ep=read('eeprom.bin'),hash=b=>createHash('sha256').update(b).digest('hex');
assert.equal(hash(sourceRaw),score.source.sha256);
assert.equal(hash(rom),meta.flashSha256);assert.equal(hash(ep),meta.eepromSha256);
const ppqn=source.ppqn,start=score.source.firstSourceQuarterBeat*ppqn;
const stop=score.source.lastSourceQuarterBeat*ppqn,end=stop-start;
const unitTicks=ppqn/score.source.gridUnitsPerQuarter;
const tempos=source.tracks.flatMap(t=>t.events.filter(e=>e.type==='tempo'));
assert.equal(tempos.length,1);assert.equal(tempos[0].tick,0);
const secondsPerTick=tempos[0].microsecondsPerQuarter/1e6/ppqn;
const original=[];
for(const track of source.tracks){
  const active=new Map();let noteId=0;
  for(const e of track.events){
    if(e.type!=='noteOn'&&e.type!=='noteOff')continue;
    const key=`${e.channel}:${e.note}`;
    if(e.type==='noteOn'&&e.velocity){
      const queue=active.get(key)||[];queue.push({...e,id:`${track.index}:${noteId++}`});active.set(key,queue);
    }else{
      assert.ok(active.get(key)?.length,'Every original Note Off has a Note On');
      const on=active.get(key).shift();
      if(on.tick>=start&&on.tick<stop)original.push({id:on.id,track:track.index,channel:on.channel,
        pitch:on.note,on:on.tick-start,off:e.tick-start,velocity:on.velocity,offVelocity:e.velocity});
    }
  }
  assert.ok([...active.values()].every(q=>q.length===0));
}
original.sort((a,b)=>a.on-b.on||a.track-b.track||a.pitch-b.pitch);
assert.equal(original.length,1027);
assert.ok(original.every(n=>n.on%unitTicks===0&&n.off%unitTicks===0));

const names=['lead','rhythmGuitar','bass'],addresses=meta.releaseChannels.voiceAddresses.slice(0,3);
const midi=name=>12*(Number(name.at(-1))+1)+{C:0,D:2,E:4,F:5,G:7,A:9,B:11}[name[0]]+Number(name.includes('#'));
const durations=[1,2,3,4,6,8,16],commands=[],played=[],held=[null,null,null];let unit=0;
function close(role,tick){if(held[role]){held[role].off=tick;held[role]=null;}}
function attack(role,pitch){
  close(role,unit*unitTicks);
  const n={role:names[role],pitch,on:unit*unitTicks,off:null};played.push(n);held[role]=n;
}
for(const phrase of meta.score.playlist){
  let at=meta.labels['section_'+phrase];
  for(;;){
    const token=rom[at++];commands.push({token,unit});
    if(token===255)break;
    if(token<224){
      const note=token>>3;
      if(note===meta.score.rest_index)close(0,unit*unitTicks);
      else if(note!==meta.score.hold_index)attack(0,midi(meta.score.pitches[note]));
      unit+=durations[token&7];
    }else if(token<240){
      const voicing=meta.score.chord_notes[meta.score.chords[token&15]];
      attack(1,voicing[0]);attack(2,voicing[1]);
    }else for(let role=0;role<3;role++)if(token&(1<<role))close(role,unit*unitTicks);
  }
}
assert.ok(played.every(n=>n.off!==null));
const countBy=(items,key)=>{
  const result=new Map();for(const item of items){const k=key(item);result.set(k,(result.get(k)||0)+1);}return result;
};
const intersection=(a,b,key)=>{
  const aa=countBy(a,key),bb=countBy(b,key);let result=0;
  for(const [k,n] of aa)result+=Math.min(n,bb.get(k)||0);return result;
};
const attackKey=n=>`${n.pitch}@${n.on}`,gateKey=n=>`${attackKey(n)}..${n.off}`;
const matchedAttacks=intersection(original,played,attackKey),matchedGates=intersection(original,played,gateKey);
// Attribute maximum one-to-one matches to parts, keeping exact gates first.
// Ambiguous same-pitch/onset unisons prefer track 0 for lead, track 1 otherwise.
const matchedOriginal=new Map(),usedArrangement=new Set();
for(const key of [gateKey,attackKey])for(const note of played){
  if(usedArrangement.has(note))continue;
  const candidates=original.filter(n=>!matchedOriginal.has(n.id)&&key(n)===key(note))
    .sort((a,b)=>(note.role==='lead'?a.track-b.track:b.track-a.track));
  if(candidates.length){matchedOriginal.set(candidates[0].id,note);usedArrangement.add(note);}
}
assert.equal(matchedOriginal.size,matchedAttacks);
assert.equal([...matchedOriginal].filter(([id,note])=>gateKey(original.find(n=>n.id===id))===gateKey(note)).length,matchedGates);
const guitarPlayed=played.filter(n=>n.role!=='bass');
const selectedSource=new Map(),leadDetails=[];
for(const note of played.filter(n=>n.role==='lead')){
  const candidates=original.filter(n=>n.pitch===note.pitch&&n.on<=note.on&&note.on<n.off)
    .sort((a,b)=>a.track-b.track||b.on-a.on);
  assert.ok(candidates.length,'Every lead pitch comes from a currently active source note');
  const selected=candidates[0];selectedSource.set(selected.id,selected);
  leadDetails.push({played:note,source:selected,exactOn:note.on===selected.on,exactOff:note.off===selected.off});
}
const peak=notes=>{
  let active=0,result=0;
  const events=notes.flatMap(n=>[[n.on,1],[n.off,-1]]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
  for(const [,delta] of events){active+=delta;result=Math.max(active,result);}return result;
};
let sourcePitchTicks=0,playedPitchTicks=0,commonPitchTicks=0;
for(let tick=0;tick<end;tick+=unitTicks){
  const a=original.filter(n=>n.on<=tick&&tick<n.off),b=played.filter(n=>n.on<=tick&&tick<n.off);
  sourcePitchTicks+=a.length*unitTicks;playedPitchTicks+=b.length*unitTicks;
  commonPitchTicks+=intersection(a,b,n=>n.pitch)*unitTicks;
}
const sourceAttackKeys=new Set(original.map(attackKey)),sourceGateKeys=new Set(original.map(gateKey));
const detail=n=>({role:n.role,pitch:n.pitch,onSeconds:n.on*secondsPerTick,offSeconds:n.off*secondsPerTick});
const byTrack=source.tracks.map(track=>{
  const notes=original.filter(n=>n.track===track.index),chosen=[...selectedSource.values()].filter(n=>n.track===track.index);
  const lead=leadDetails.filter(n=>n.source.track===track.index);
  const matched=notes.filter(n=>matchedOriginal.has(n.id));
  return {track:track.index,name:track.events.find(e=>e.type==='text'&&e.metaType===3)?.text,
    sourceNotes:notes.length,sourceChordAttacks:new Set(notes.map(n=>n.on)).size,
    exactSourceAttacksInAnyTonalRole:matched.length,
    exactSourceGatesInAnyTonalRole:matched.filter(n=>n.off===matchedOriginal.get(n.id).off).length,
    sourceAttacksMatchedByRole:Object.fromEntries(names.map(role=>[role,matched.filter(n=>matchedOriginal.get(n.id).role===role).length])),
    uniqueSourceNotesUsedByLead:chosen.length,leadRetriggers:lead.length,
    leadExactSourceOnOff:lead.filter(n=>n.exactOn&&n.exactOff).length,
    notUsedByLead:notes.length-chosen.length};
});
console.log(JSON.stringify({stage:'source comparison',sourceNotes:original.length,encodedAttacks:played.length,
  exactPitchAndOnset:matchedAttacks,exactPitchOnsetAndGate:matchedGates,originalTracks:byTrack}));

// Execute the actual binary once. Record initialized pitches and true held-gate
// changes rather than counting release slots as additional Note On events.
const core=new AVRCore(rom,ep),pc=Object.fromEntries(Object.entries(meta.labels).map(([k,v])=>[k,v/2]));
const actual=[],actualHeld=[null,null,null],seen=[],run=core.step.bind(core);
let pending=null,finished=false,anchor=null;
function actualClose(role){if(actualHeld[role]){actualHeld[role].offCycle=core.cyc;actualHeld[role]=null;}}
function checkReleases(){for(let role=0;role<3;role++)if(!(core.data[addresses[role]]&128))actualClose(role);}
core.step=()=>{
  if(!finished&&!core.inIRQ){
    if(core.pc===pc.read_event){
      checkReleases();const token=rom[core.r[30]|core.r[31]<<8];
      anchor??=core.cyc;seen.push(token);if(seen.length===commands.length)finished=true;
    }
    if(core.pc===pc.hold_sample)checkReleases();
    if(core.pc===pc.initialize_voice){pending=addresses.indexOf(core.r[26]);assert.ok(pending>=0);}
    if(core.pc===pc.voice_initialized){
      const role=pending,a=addresses[role],step=core.data[a+3]|core.data[a+4]<<8;
      actualClose(role);
      const frequency=step*18750/65536,pitch=Math.round(69+12*Math.log2(frequency/440));
      const note={role:names[role],pitch,step,frequency,onCycle:core.cyc,offCycle:null,
        centsError:1200*Math.log2(frequency/(440*2**((pitch-69)/12)))};
      actual.push(note);actualHeld[role]=note;pending=null;
    }
  }
  run();
};
while(!finished&&core.cyc<9600000*33)core.nextDuty();
assert.ok(finished);assert.deepEqual(seen,commands.map(c=>c.token));
assert.equal(actual.length,played.length);assert.equal(core.lost+core.workLost,0);
// Chord commands precede the lead command at the same tick, so compare role
// streams separately instead of imposing an invented inter-channel ordering.
let maxOnError=0,maxOffError=0,maxDurationError=0,maxPitchError=0;
for(const role of names){
  const expected=played.filter(n=>n.role===role),observed=actual.filter(n=>n.role===role);
  assert.equal(observed.length,expected.length);
  for(let i=0;i<expected.length;i++){
    const a=observed[i],e=expected[i];assert.equal(a.pitch,e.pitch);assert.notEqual(a.offCycle,null);
    maxOnError=Math.max(maxOnError,Math.abs((a.onCycle-anchor)/9600000-e.on*secondsPerTick)*1000);
    maxOffError=Math.max(maxOffError,Math.abs((a.offCycle-anchor)/9600000-e.off*secondsPerTick)*1000);
    maxDurationError=Math.max(maxDurationError,Math.abs((a.offCycle-a.onCycle)/9600000-(e.off-e.on)*secondsPerTick)*1000);
    maxPitchError=Math.max(maxPitchError,Math.abs(a.centsError));
  }
}
const timeSignatures=source.tracks.flatMap(t=>t.events.filter(e=>e.type==='timeSignature')
  .map(e=>({track:t.index,tick:e.tick,numerator:e.numerator,denominator:e.denominator})))
  .sort((a,b)=>a.tick-b.tick||a.track-b.track);
const signatureAtStart=timeSignatures.filter(m=>m.tick<=start).at(-1);
const excerptMeters=[...(signatureAtStart?[signatureAtStart]:[]),...timeSignatures.filter(m=>m.tick>start&&m.tick<stop)];
assert.ok(excerptMeters.length);
let audioVerification=null;
if(process.argv[2]){
  const audio=fs.readFileSync(process.argv[2]);
  assert.equal(audio.toString('ascii',0,4),'RIFF');assert.equal(audio.toString('ascii',8,12),'WAVE');
  assert.equal(audio.readUInt16LE(20),1);assert.equal(audio.readUInt16LE(22),1);
  assert.equal(audio.readUInt32LE(24),48000);assert.equal(audio.readUInt16LE(34),16);
  assert.equal(audio.readUInt32LE(40),audio.length-44);
  const seconds=(audio.length-44)/audio.readUInt32LE(28);assert.ok(seconds>=30&&seconds<=33);
  const temp=path.join(root,'build/mariachi-source-audit-audio');fs.mkdirSync(temp,{recursive:true});
  for(const file of ['synth.hex','eeprom.hex','build-report.json'])fs.copyFileSync(path.join(folder,file),path.join(temp,file));
  const result=spawnSync(process.execPath,[path.join(root,'tools/render-firmware-preview.mjs'),temp,String(seconds)],
    {cwd:root,encoding:'utf-8'});
  assert.equal(result.status,0,result.stdout+result.stderr);
  const regenerated=fs.readFileSync(path.join(temp,'preview.wav'));
  assert.equal(hash(audio),hash(regenerated),'The supplied listening file must reproduce from this exact firmware');
  audioVerification={file:path.basename(process.argv[2]),seconds,sampleRate:48000,sha256:hash(audio),
    bitIdenticalToNewRender:true,render:JSON.parse(result.stdout)};
}
const report={scope:'Current reduced AVR image compared with the retained third-party two-guitar transcription; not an authenticated film score or recording.',
  sourceJsonSha256:hash(sourceRaw),sourceMidiSha256:source.source.sha256,flashSha256:hash(rom),eepromSha256:hash(ep),
  audioVerification,
  excerpt:{firstSourceQuarterBeat:start/ppqn,lastSourceQuarterBeat:stop/ppqn,musicSeconds:end*secondsPerTick,
    loopSeconds:unit*unitTicks*secondsPerTick,sourceNoteCount:original.length,sourcePeakPolyphony:peak(original)},
  originalTracks:byTrack,
  arrangement:{tonalAttacks:played.length,attacksByRole:Object.fromEntries(names.map(r=>[r,played.filter(n=>n.role===r).length])),
    primaryHeldPolyphony:peak(played),releaseSlots:2,percussionAdded:true,
    allLeadNotesFromCurrentlyActiveSource:true,uniqueOriginalNotesUsedByLead:selectedSource.size,
    leadExtraRetriggers:played.filter(n=>n.role==='lead').length-selectedSource.size,
    instrumentAssignments:meta.instrumentAssignments},
  comparison:{definition:'Maximum multiset matches at exact original tick/pitch; ignores timbre and release tails. A played attack matches at most one source attack.',
    exactPitchAndOnset:matchedAttacks,exactPitchOnsetAndGate:matchedGates,
    omittedOrDisplacedOriginalAttacks:original.length-matchedAttacks,
    addedOrDisplacedArrangementAttacks:played.length-matchedAttacks,
    originalAttackRecallPercent:100*matchedAttacks/original.length,
    exactGuitarPitchAndOnset:intersection(original,guitarPlayed,attackKey),
    exactGuitarPitchOnsetAndGate:intersection(original,guitarPlayed,gateKey),
    heldPitchTime:{definition:'One-to-one active pitch multiplicities on the exact source tick grid; includes bass, excludes percussion/release tails.',
      sourcePitchTicks,playedPitchTicks,commonPitchTicks,recallPercent:100*commonPitchTicks/sourcePitchTicks,
      precisionPercent:100*commonPitchTicks/playedPitchTicks}},
  meter:{sourceTimeSignatures:timeSignatures,configuredSourceMeter:score.sourceMeters,
    signaturesApplicableToExcerpt:excerptMeters,
    decoderStorageBeatsPerBar:score.beats_per_bar,addedDrumPatternQuarterBeats:2,
    sourceMeterMetadataMatches:excerptMeters.every(m=>`${m.numerator}/${m.denominator}`===score.sourceMeters)},
  actualAvrPlayback:{commandsVerified:seen.length,tonalAttacksVerified:actual.length,allPitchesMatchEncodedArrangement:true,
    maximumOnsetErrorMs:maxOnError,maximumGateEndErrorMs:maxOffError,maximumGateDurationErrorMs:maxDurationError,
    maximumPitchQuantizationErrorCents:maxPitchError,lostTimerEvents:core.lost,lostWorkEvents:core.workLost,
    precisionScope:'Timing against the encoded arrangement, not against omitted original notes; cents error uses the nominal 9.6 MHz clock.'},
  examples:{leadRetimedOrShortened:leadDetails.filter(n=>!n.exactOn||!n.exactOff).slice(0,8).map(n=>({played:detail(n.played),
      original:{track:n.source.track,pitch:n.source.pitch,onSeconds:n.source.on*secondsPerTick,offSeconds:n.source.off*secondsPerTick}})),
    accompanimentWithoutExactSourceAttack:played.filter(n=>n.role!=='lead'&&!sourceAttackKeys.has(attackKey(n))).slice(0,8).map(detail),
    matchingAttackWithChangedGate:played.filter(n=>sourceAttackKeys.has(attackKey(n))&&!sourceGateKeys.has(gateKey(n))).slice(0,8).map(detail)},
  limitations:['No percentage here is a perceptual similarity score.',
    'The source is a third-party transcription; fidelity of that transcription to the soundtrack is not established.',
    'Compact measured guitar profiles approximate a timbre; they do not reproduce the original guitar recording.',
    'The eight-voice feasibility probe and lossless note packets are not the current AVR song player.']};
const output=path.join(root,'web-player/reports/cancion-del-mariachi-source-comparison.json');
fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({excerpt:report.excerpt,originalTracks:report.originalTracks,
  arrangement:{...report.arrangement,instrumentAssignments:undefined},comparison:report.comparison,meter:report.meter,
  actualAvrPlayback:report.actualAvrPlayback},null,2));
