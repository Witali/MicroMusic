import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compareVerificationEvents,VERIFICATION_EVENT_TOLERANCE_PS} from '../scripts/lib/avr-verification-events.mjs';

const options={configuration:'verification',device:'attiny13a'};
const edge=(timePs,extra={})=>({timePs,kind:'pin',pin:0,level:1,...extra});
const compare=(reference,actual,configuration=options)=>compareVerificationEvents(reference,actual,configuration);

test('ATtiny13A verification has a fixed inclusive 10000 ps event tolerance',()=>{
  assert.equal(VERIFICATION_EVENT_TOLERANCE_PS,10000n);
  for(const offset of [-10000n,0n,10000n]){
    const result=compare([edge(20000n)],[edge(20000n+offset)]);
    assert.deepEqual(result,{eventCount:1,maxErrorPs:offset<0n?-offset:offset,tolerancePs:10000n});
  }
  for(const offset of [-10001n,10001n])assert.throws(()=>compare([edge(20000n)],[edge(20000n+offset)]),/exceeds 10 ns/);
});

test('global time anchors and cumulative drift cannot be repaired by first-event alignment or per-step tolerance',()=>{
  assert.throws(()=>compare([edge(1000000n)],[edge(1010001n)]),/exceeds 10 ns/);
  const reference=[0n,100000n,200000n].map(time=>edge(time));
  const actual=[0n,105001n,210002n].map(time=>edge(time));
  assert.throws(()=>compare(reference,actual),/ordinal 2/);
  const accepted=[0n,105000n,210000n].map(time=>edge(time));
  assert.equal(compare(reference,accepted).maxErrorPs,10000n);
});

test('event order, identity, levels, cycle counters and every flag remain exact even within the tolerance',()=>{
  const reference=[edge(0n,{kind:'clock',cycle:1n,flags:{sreg:0x80}}),edge(1n,{kind:'compare',cycle:2n,flags:{sreg:0x81}})];
  for(const mutate of [
    events=>events.reverse(),events=>events[0].level=0,events=>events[0].pin=1,
    events=>events[0].kind='compare',events=>events[0].cycle=2n,
    events=>events[0].flags.sreg=0x81,events=>events[0].extra=0,
    events=>delete events[0].flags,
  ]){
    const actual=structuredClone(reference);mutate(actual);
    // Preserve nondecreasing times so a reordered trace must fail discrete identity.
    actual.forEach((event,n)=>event.timePs=BigInt(n));
    assert.throws(()=>compare(reference,actual),/state\/order/);
  }
});

test('ties preserve ordinal identity without greedy matching and permit exact same-time events',()=>{
  const reference=[edge(10000n,{kind:'rise'}),edge(10000n,{kind:'fall',level:0})];
  assert.equal(compare(reference,reference.map(event=>({...event,timePs:'20000'}))).eventCount,2);
  assert.throws(()=>compare(reference,[reference[1],reference[0]]),/state\/order/);
});

test('lost and extra edges reject instead of being matched to another nearby event',()=>{
  const events=[edge(0n),edge(1n,{level:0}),edge(2n)];
  assert.throws(()=>compare(events,events.slice(1)),/count/);
  assert.throws(()=>compare(events,[...events,edge(3n)]),/count/);
  assert.throws(()=>compare([edge(0n),edge(2n)],[edge(0n),edge(1n,{level:0})]),/state\/order/);
});

test('both traces must be nondecreasing while equal timestamps are valid',()=>{
  assert.equal(compare([edge(2n),edge(2n)],[edge(2n),edge(2n)]).eventCount,2);
  for(const traces of [ [[edge(2n),edge(1n)],[edge(2n),edge(2n)]],
    [[edge(2n),edge(2n)],[edge(2n),edge(1n)]] ])assert.throws(()=>compare(...traces),/nondecreasing/);
});

test('bigint and canonical string timestamps above Number precision and at uint64 limits compare exactly',()=>{
  const big=9007199254740993n,max=0xffffffffffffffffn;
  const result=compare([edge(big),edge(max-10000n)],[edge(big.toString()),edge(max.toString())]);
  assert.equal(result.maxErrorPs,10000n);assert.equal(compare([edge(0n)],[edge('0')]).maxErrorPs,0n);
  for(const value of [-1n,max+1n,'18446744073709551616'])assert.throws(()=>compare([edge(value)],[edge(0n)]),/uint64/);
});

test('Number timestamps and noncanonical decimal strings never enter the comparison',()=>{
  for(const value of [0,1,Number.MAX_SAFE_INTEGER+1,NaN,Infinity,'','00','01','+0','-0','-1',' 1','1 ',
    '1.0','1e3','0x10','1\n',null,undefined,{},true]){
    assert.throws(()=>compare([edge(value)],[edge(0n)]),/timePs|metadata/);
    assert.throws(()=>compare([edge(0n)],[edge(value)]),/timePs|metadata/);
  }
});

test('malformed trace entries and nonstructured event fields reject without mutation or getters',()=>{
  for(const reference of [null,{},'trace',[null],[[]],[{}],[{kind:'edge'}],Array(1)])assert.throws(()=>compare(reference,[]),/trace|metadata/);
  for(const value of [undefined,NaN,Infinity,()=>0,Symbol('value'),new Date(),new Map(),Array(1),
    Object.assign(Array(1),{extra:0}),Object.assign(Array(1),{'0.5':0})])
    assert.throws(()=>compare([edge(0n,{state:value})],[edge(0n)]),/metadata/);
  const cyclic={};cyclic.self=cyclic;assert.throws(()=>compare([edge(0n,{state:cyclic})],[edge(0n)]),/metadata/);
  let accessed=false;const event={kind:'pin'};Object.defineProperty(event,'timePs',{enumerable:true,get(){accessed=true;return 0n;}});
  assert.throws(()=>compare([event],[edge(0n)]),/metadata/);assert.equal(accessed,false);
  const hidden=edge(0n);Object.defineProperty(hidden,'state',{value:1});assert.throws(()=>compare([hidden],[edge(0n)]),/metadata/);
});

test('discrete counters reject unsafe integer Numbers at every depth while bigint and fractional state remain exact',()=>{
  for(const cycle of [Number.MAX_SAFE_INTEGER+1,1e20,-1e20]){
    const events=[edge(0n,{state:{nested:[{cycle}]}})];assert.throws(()=>compare(events,events),/metadata/);
  }
  const events=[edge(0n,{state:{nested:[{cycle:100000000000000000000n}],voltage:1.25,code:Number.MAX_SAFE_INTEGER}})];
  assert.equal(compare(events,structuredClone(events)).eventCount,1);
});

test('outer trace arrays reject index getters without executing or mutating either trace',()=>{
  for(const side of ['reference','actual']){
    let calls=0;const other=[edge(0n)],accessor=[];
    Object.defineProperty(accessor,'0',{enumerable:true,configurable:true,get(){calls++;other[0].level=0;return edge(0n);}});
    const traces=side==='reference'?[accessor,other]:[other,accessor];
    assert.throws(()=>compare(...traces),/trace array/);assert.equal(calls,0);assert.equal(other[0].level,1);
  }
});

test('outer trace arrays require dense enumerable data indices and reject extra or hidden entries',()=>{
  const hidden=[edge(0n)];Object.defineProperty(hidden,'0',{enumerable:false});
  const extra=Object.assign([edge(0n)],{extra:edge(0n)});
  const maskedHole=Object.assign(Array(1),{extra:edge(0n)});
  const symbolic=[edge(0n)];symbolic[Symbol('extra')]=edge(0n);
  for(const malformed of [hidden,extra,maskedHole,symbolic]){
    assert.throws(()=>compare(malformed,[edge(0n)]),/trace array/);
    assert.throws(()=>compare([edge(0n)],malformed),/trace array/);
  }
});

test('site mode, other devices, malformed options and caller tolerance changes reject',()=>{
  for(const config of [undefined,null,{},[],{...options,configuration:'site'},
    {...options,configuration:'precise'},{...options,device:'attiny88'},{...options,device:'ATtiny13A'},
    {...options,tolerancePs:10001n},{...options,toleranceNs:100}])assert.throws(()=>compareVerificationEvents([],[],config),/configuration/);
});

test('successful and failed comparisons leave frozen input traces and nested state untouched',()=>{
  const state=Object.freeze({cycle:42n,flags:Object.freeze([0,1,0x80]),details:Object.freeze({enabled:true})});
  const reference=Object.freeze([Object.freeze(edge(100000n,{state}))]);
  const actual=Object.freeze([Object.freeze(edge('110000',{state}))]);
  assert.equal(compare(reference,actual).maxErrorPs,10000n);
  assert.throws(()=>compare(reference,Object.freeze([Object.freeze(edge(110001n,{state}))])),/exceeds/);
  assert.equal(reference[0].timePs,100000n);assert.equal(actual[0].timePs,'110000');assert.equal(state.cycle,42n);
});

test('empty traces have zero observed error and do not prove hardware accuracy',()=>{
  assert.deepEqual(compare([],[]),{eventCount:0,maxErrorPs:0n,tolerancePs:10000n});
});
