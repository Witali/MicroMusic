import assert from 'node:assert/strict';

// This partitions sampled surviving function bodies. Compiler inlining prevents
// these ownership labels from establishing exclusive hardware-subsystem time.
const groups = new Map([
  ['generated_cpu_body','generated_cpu_body'],
  ['native_board_body','mixed_native_container'],
  ['native_bridge_body','mixed_native_container'],
  ['native_clki_body','mixed_native_container'],
  ['native_timer0_body','native_peripheral_body'],
  ['native_gpio_body','native_peripheral_body'],
  ['native_analog_body','native_peripheral_body'],
  ['native_other_peripheral_body','native_peripheral_body'],
  ['native_pin_body','native_pin_body'],
  ['native_audio_body','native_audio_body'],
  ['native_support_body','native_support_body'],
]);
const safeTime = value => Number.isSafeInteger(value) && value >= 0;
const percentage = (value,total) => total ? 100*value/total : 0;
function quantile(sorted,fraction) {
  return sorted.length ? sorted[Math.max(0,Math.ceil(sorted.length*fraction)-1)] : null;
}
function median(sorted) {
  return sorted.length ? (sorted.length%2 ? sorted[sorted.length>>1] :
    (sorted[sorted.length/2-1]+sorted[sorted.length/2])/2) : null;
}
function bucket() { return {samples:0,deltaWeightUs:0,categories:new Map(),groups:new Map(),callerContext:new Map()}; }
function add(map,key,weight) {
  const row=map.get(key)??{samples:0,deltaWeightUs:0};
  row.samples++;row.deltaWeightUs+=weight;map.set(key,row);
}
function finishBucket(value) {
  const rows=map=>[...map].map(([category,row])=>({category,...row,
    samplePercent:percentage(row.samples,value.samples),
    deltaWeightPercent:percentage(row.deltaWeightUs,value.deltaWeightUs)}))
    .sort((a,b)=>b.samples-a.samples||(a.category<b.category?-1:a.category>b.category?1:0));
  return {samples:value.samples,deltaWeightUs:value.deltaWeightUs,
    categories:rows(value.categories),groups:rows(value.groups),
    // This is a second view of support/unknown leaves, never additional cost.
    ambiguousLeafCallerContext:rows(value.callerContext)};
}
function frameInfo(frame,known) {
  assert.ok(frame && typeof frame.functionName==='string','Invalid call frame');
  const name=frame.functionName.replace(/^\$/,''),match=known.get(name);
  if(match)return {category:match,group:groups.get(match),known:true};
  const url=typeof frame.url==='string'?frame.url.replaceAll('\\','/') : '';
  if(url.startsWith('wasm:'))return {category:'unresolved_wasm',group:'unknown_wasm'};
  if(name==='(garbage collector)')return {category:'v8_gc',group:'vm_gc'};
  if(name==='(idle)')return {category:'v8_idle',group:'vm_idle'};
  if(/\/(?:attiny13a-runtime|avr-runtime|avr-transpiled-runtime)\.js$/.test(url))
    return {category:'javascript_bridge',group:'javascript_bridge'};
  if(/profile-device\.mjs$/.test(url)||url.startsWith('node:inspector'))
    return {category:'profiler_harness',group:'profiler_harness'};
  return {category:'other_js_vm',group:'other_js_vm'};
}
function isWorkFrame(frame,operation) {
  const url=typeof frame.url==='string'?frame.url.replaceAll('\\','/') : '';
  return operation==='capture' ? frame.functionName==='capturePhysical'&&/\/attiny13a-runtime\.js$/.test(url) :
    frame.functionName==='run'&&/\/(?:avr-transpiled-runtime|attiny13a-runtime)\.js$/.test(url);
}

export function attributeAvrProfile(profile,{functions=[],operation='capture',requestedIntervalUs=null}={}) {
  assert.ok(operation==='capture'||operation==='direct','Invalid profile operation');
  assert.ok(requestedIntervalUs===null||(safeTime(requestedIntervalUs)&&requestedIntervalUs>0),'Invalid requested sampling interval');
  assert.ok(Array.isArray(functions),'Function metadata must be an array');
  const known=new Map();
  for(const fn of functions) {
    assert.ok(typeof fn.name==='string'&&fn.name&&!known.has(fn.name),'Duplicate or invalid function metadata');
    assert.ok(groups.has(fn.category),'Unknown function ownership category');
    known.set(fn.name,fn.category);
  }
  assert.ok(profile && Array.isArray(profile.nodes)&&profile.nodes.length,'Profile nodes are required');
  assert.ok(Array.isArray(profile.samples)&&Array.isArray(profile.timeDeltas),'Samples and timeDeltas are required');
  assert.equal(profile.samples.length,profile.timeDeltas.length,'Sample/delta length mismatch');
  assert.ok(safeTime(profile.startTime)&&safeTime(profile.endTime)&&profile.endTime>=profile.startTime,'Invalid profile timestamps');
  const nodes=new Map(),parents=new Map(),frames=new Map();
  for(const node of profile.nodes) {
    assert.ok(safeTime(node.id)&&!nodes.has(node.id),'Duplicate or invalid profile node ID');
    assert.ok(node.children===undefined||Array.isArray(node.children),'Invalid node children');
    nodes.set(node.id,node);frames.set(node.id,frameInfo(node.callFrame,known));
  }
  for(const node of nodes.values())for(const child of node.children??[]) {
    assert.ok(nodes.has(child),'Missing child node');
    assert.ok(!parents.has(child),'Multiple parents or duplicate child');
    parents.set(child,node.id);
  }
  const roots=[...nodes.keys()].filter(id=>!parents.has(id));
  assert.equal(roots.length,1,'Profile tree must have one root');
  // Validate unsampled components too; an orphan cycle must not pass silently.
  const reached=new Set(),pending=[roots[0]];
  while(pending.length) {
    const id=pending.pop();assert.ok(!reached.has(id),'Profile tree cycle');reached.add(id);
    for(const child of nodes.get(id).children??[])pending.push(child);
  }
  assert.equal(reached.size,nodes.size,'Disconnected nodes or profile tree cycle');
  const durationUs=profile.endTime-profile.startTime;
  let deltaSpanUs=0;
  for(const delta of profile.timeDeltas) {
    assert.ok(safeTime(delta),'Invalid sample delta');deltaSpanUs+=delta;
    assert.ok(Number.isSafeInteger(deltaSpanUs)&&deltaSpanUs<=durationUs,'Sample deltas exceed profile duration');
  }
  const all=bucket(),work=bucket(),withoutWork=bucket();
  let ownershipChangeGapUs=0,previousCategory;
  for(const [index,id]of profile.samples.entries()) {
    assert.ok(nodes.has(id),'Missing sampled node');
    const leaf=frames.get(id),weight=profile.timeDeltas[index];
    let inWork=false,callerContext=null;
    for(let at=id;at!==undefined;at=parents.get(at)) {
      if(isWorkFrame(nodes.get(at).callFrame,operation))inWork=true;
      const frame=frames.get(at);
      if(at!==id&&callerContext===null&&frame.known&&frame.category!=='native_support_body')callerContext=frame.category;
    }
    if(previousCategory!==undefined&&previousCategory!==leaf.category)ownershipChangeGapUs+=weight;
    previousCategory=leaf.category;
    for(const target of [all,inWork?work:withoutWork]) {
      target.samples++;target.deltaWeightUs+=weight;
      add(target.categories,leaf.category,weight);add(target.groups,leaf.group,weight);
      if(leaf.category==='native_support_body'||leaf.category==='unresolved_wasm')
        add(target.callerContext,callerContext??'no_known_caller',weight);
    }
  }
  const sorted=[...profile.timeDeltas].sort((a,b)=>a-b);
  const gaps=requestedIntervalUs===null?null:{requestedIntervalUs,
    overTwiceRequested:sorted.filter(delta=>delta>2*requestedIntervalUs).length,
    overTenTimesRequested:sorted.filter(delta=>delta>10*requestedIntervalUs).length};
  return {
    schema:'micromusic-avr-profile-attribution-v1',
    exclusiveSubsystemTimeAvailable:false,
    method:{unit:'Disjoint observed surviving-function leaf ownership.',
      deltaWeights:'Estimates only: each recorded delta is assigned to its right-end sample, including the first delay. A sample does not prove ownership throughout that interval.',
      context:'Nearest known non-support caller for support/unknown WASM leaves is a separate contextual view, not exclusive cost; do not add it to the leaf budget.',
      limits:'O3/V8 inlining stays in its containing body. Work ancestry excludes unrooted GC/VM samples even when they occurred during work. No confidence interval or unprofiled speed is inferred.'},
    timeline:{durationUs,deltaSpanUs,unrepresentedTailUs:durationUs-deltaSpanUs,
      firstSampleDelayUs:profile.timeDeltas[0]??null,
      deltaStreamSpanPercent:percentage(deltaSpanUs,durationUs),ownershipChangeGapUs},
    deltas:{count:sorted.length,minUs:sorted[0]??null,medianUs:median(sorted),
      p95Us:quantile(sorted,.95),p99Us:quantile(sorted,.99),maxUs:sorted.at(-1)??null,
      zeroCount:sorted.filter(delta=>delta===0).length,gaps},
    all:finishBucket(all),workAncestry:finishBucket(work),withoutWorkAncestry:finishBucket(withoutWork),
  };
}
