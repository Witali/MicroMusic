import {test} from 'node:test';
import assert from 'node:assert/strict';
import {attributeAvrProfile} from '../scripts/lib/avr-profile-attribution.mjs';

const fn=(id,name,children=[],url='wasm://diagnostic')=>({id,callFrame:{functionName:name,url},children});
const functions=[
  {name:'cpu.block_0x0000',category:'generated_cpu_body',object:'DO_NOT_COPY_PRIVATE_OBJECT'},
  {name:'native.device.advance_to',category:'native_board_body'},
  {name:'native.timer0.event_distance',category:'native_timer0_body'},
  {name:'native.support.__multi3',category:'native_support_body'},
  {name:'native.device.capture_pins',category:'native_pin_body'},
];
function fixture() {
  return {startTime:100,endTime:160,
    nodes:[fn(1,'(root)',[2,9,10],''),
      fn(2,'capturePhysical',[3],'file:///PRIVATE_DIRECTORY/web-player/lib/attiny13a-runtime.js'),
      fn(3,'$cpu.block_0x0000',[4,8]),fn(4,'native.device.advance_to',[5,7]),
      fn(5,'native.timer0.event_distance',[6]),fn(6,'native.support.__multi3'),
      fn(7,'wasm-function[999]'),fn(8,'native.device.capture_pins'),
      fn(9,'(garbage collector)',[],''),fn(10,'post',[],'node:inspector/promises')],
    samples:[3,4,5,6,7,8,9,10],timeDeltas:[2,8,4,10,3,5,20,1]};
}
const analyze=profile=>attributeAvrProfile(profile,{functions,requestedIntervalUs:2});
test('leaf sample and delta budgets partition all, work and non-work observations',()=>{
  const result=analyze(fixture());
  assert.equal(result.exclusiveSubsystemTimeAvailable,false);
  assert.equal(result.all.samples,8);assert.equal(result.all.deltaWeightUs,53);
  assert.equal(result.workAncestry.samples,6);assert.equal(result.workAncestry.deltaWeightUs,32);
  assert.equal(result.withoutWorkAncestry.samples,2);assert.equal(result.withoutWorkAncestry.deltaWeightUs,21);
  for(const bucket of [result.all,result.workAncestry,result.withoutWorkAncestry])for(const key of ['categories','groups']) {
    assert.equal(bucket[key].reduce((n,row)=>n+row.samples,0),bucket.samples);
    assert.equal(bucket[key].reduce((n,row)=>n+row.deltaWeightUs,0),bucket.deltaWeightUs);
  }
  assert.ok(result.all.groups.some(row=>row.category==='mixed_native_container'&&row.samples===1));
  assert.ok(result.all.groups.some(row=>row.category==='unknown_wasm'&&row.samples===1));
  assert.ok(result.withoutWorkAncestry.groups.some(row=>row.category==='vm_gc'&&row.samples===1));
  assert.doesNotMatch(JSON.stringify(result),/PRIVATE_DIRECTORY|DO_NOT_COPY_PRIVATE_OBJECT|wasm-function\[999\]/);
});
test('irregular delta diagnostics retain unrepresented tail and boundary sensitivity',()=>{
  const result=analyze(fixture());
  assert.deepEqual(result.timeline,{durationUs:60,deltaSpanUs:53,unrepresentedTailUs:7,
    firstSampleDelayUs:2,deltaStreamSpanPercent:100*53/60,ownershipChangeGapUs:51});
  assert.deepEqual(result.deltas,{count:8,minUs:1,medianUs:4.5,p95Us:20,p99Us:20,maxUs:20,
    zeroCount:0,gaps:{requestedIntervalUs:2,overTwiceRequested:4,overTenTimesRequested:0}});
});
test('support and unresolved WASM caller context is labelled separately from the leaf budget',()=>{
  const result=analyze(fixture()),rows=result.workAncestry.ambiguousLeafCallerContext;
  assert.deepEqual(rows.map(({category,samples,deltaWeightUs})=>({category,samples,deltaWeightUs})),[
    {category:'native_board_body',samples:1,deltaWeightUs:3},
    {category:'native_timer0_body',samples:1,deltaWeightUs:10},
  ]);
  assert.equal(result.workAncestry.samples,6);
  const profile=fixture();
  profile.nodes[0].children.push(11);profile.nodes.push(fn(11,'unmapped'));
  profile.samples.push(11);profile.timeDeltas.push(0);
  assert.ok(analyze(profile).all.ambiguousLeafCallerContext.some(row=>row.category==='no_known_caller'));
});
test('nested support frames retain their nearest non-support caller without inheriting cost',()=>{
  const profile=fixture();profile.nodes[5].children=[11];
  profile.nodes.push(fn(11,'native.support.__multi3'));profile.samples[3]=11;
  const result=analyze(profile);
  assert.ok(result.workAncestry.ambiguousLeafCallerContext.some(row=>row.category==='native_timer0_body'&&row.samples===1));
  assert.equal(result.workAncestry.categories.find(row=>row.category==='native_timer0_body').samples,1);
  assert.equal(result.workAncestry.categories.find(row=>row.category==='native_support_body').samples,1);
});
test('direct work recognizes run in either runtime and capture remains separate',()=>{
  for(const filename of ['avr-transpiled-runtime','attiny13a-runtime']) {
    const profile=fixture();profile.nodes[1].callFrame={functionName:'run',url:`file:///repo/${filename}.js`};
    assert.equal(attributeAvrProfile(profile,{functions,operation:'direct'}).workAncestry.samples,6);
    assert.equal(analyze(profile).workAncestry.samples,0);
  }
});
test('empty and zero-delta profiles retain finite zero budgets',()=>{
  const empty={nodes:[fn(1,'(root)',[],'')],samples:[],timeDeltas:[],startTime:0,endTime:10};
  const result=attributeAvrProfile(empty);
  assert.equal(result.timeline.unrepresentedTailUs,10);assert.equal(result.deltas.minUs,null);
  assert.equal(result.all.samples,0);assert.deepEqual(result.all.categories,[]);
  empty.samples=[1];empty.timeDeltas=[0];
  const zero=attributeAvrProfile(empty);
  assert.equal(zero.all.categories[0].samplePercent,100);
  assert.equal(zero.all.categories[0].deltaWeightPercent,0);
  assert.equal(zero.deltas.zeroCount,1);
});
const malformed=[
  ['duplicate nodes',p=>p.nodes.push(p.nodes[0]),/node ID/],
  ['missing child',p=>p.nodes[0].children.push(999),/Missing child/],
  ['duplicate child',p=>p.nodes[0].children.push(2),/Multiple parents/],
  ['multiple parents',p=>p.nodes[2].children.push(9),/Multiple parents/],
  ['root cycle',p=>p.nodes[3].children.push(1),/one root/],
  ['disconnected cycle',p=>{p.nodes.push(fn(11,'a',[12]),fn(12,'b',[11]));},/Disconnected/],
  ['missing sampled node',p=>p.samples[0]=999,/Missing sampled/],
  ['delta count',p=>p.timeDeltas.pop(),/length mismatch/],
  ['missing deltas',p=>delete p.timeDeltas,/timeDeltas are required/],
  ['negative delta',p=>p.timeDeltas[0]=-1,/Invalid sample delta/],
  ['nonfinite delta',p=>p.timeDeltas[0]=NaN,/Invalid sample delta/],
  ['delta overrun',p=>p.timeDeltas[0]=100,/exceed profile duration/],
  ['reversed timestamps',p=>p.endTime=99,/Invalid profile timestamps/],
];
for(const [name,mutate,error]of malformed)test('reject malformed profile: '+name,()=>{
  const profile=fixture();mutate(profile);assert.throws(()=>analyze(profile),error);
});
test('reject ambiguous ownership metadata and invalid options',()=>{
  assert.throws(()=>attributeAvrProfile(fixture(),{functions:[functions[0],functions[0]]}),/Duplicate/);
  assert.throws(()=>attributeAvrProfile(fixture(),{functions:[{name:'new',category:'guessed_subsystem'}]}),/Unknown function ownership/);
  assert.throws(()=>attributeAvrProfile(fixture(),{operation:'guessed'}),/Invalid profile operation/);
  for(const requestedIntervalUs of [0,-1,NaN,1.5])assert.throws(()=>attributeAvrProfile(fixture(),{requestedIntervalUs}),/Invalid requested/);
});
