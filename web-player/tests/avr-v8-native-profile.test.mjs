import {test} from 'node:test';
import assert from 'node:assert/strict';
import {auditV8NativeProfile,validateV8NativeFunctions} from '../scripts/lib/avr-v8-native-profile.mjs';

const fn={name:'native.device.service',index:7,codeOffset:100,end:200};
const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
function vlq(value){let n=Math.abs(value)*2+(value<0?1:0),text='';do{const digit=n%32;n=Math.floor(n/32);text+=alphabet[digit+(n?32:0)];}while(n);return text;}
const encoded=rows=>rows.map(row=>row.map(vlq).join('')).join(',');
const makeMap=(rows=[[104,0,9,0],[8,1,10,0],[8,1,0,0]],sources=[
  'C:/confidential-prefix/project/web-player/native/peripherals/device.c',
  'C:/confidential-prefix/project/web-player/native/peripherals/../devices/attiny13a/clki_board.inc',
  'D:/confidential-support/library.c'])=>({version:3,names:[],sources,mappings:encoded(rows)});
const creation=(time=10,start='0x1000',size=64,name=fn.name)=>`code-creation,JS,4,${time},${start},${size},${name},0x2000,`;
const tick=(pc='0x1009',time=20,external=0)=>`tick,${pc},${time},${external},0x0,0`;
function disassembly({name=fn.name,index=7,base='0000000000001000',size=64,positions=[[8,4],[32,12],[48,20]],compiler='Liftoff'}={}){
  return ['--- WebAssembly code ---',`name: ${name}`,`index: ${index}`,'kind: wasm function',`compiler: ${compiler}`,
    `Instructions (size = ${size})`,`${base}     0  55  push rbp`,'Source positions:',' pc offset  position',
    ...positions.map(([offset,position])=>` ${offset.toString(16)} ${position} statement`),'','Safepoints (entries = 0)',
    '--- End code ---'].join('\n');
}
const input=extra=>({log:[creation(),tick(),tick('0x1021',30),tick('0x1031',40),tick('0x9000',50)].join('\n'),
  disassembly:disassembly(),functions:[fn],sourceMap:makeMap(),...extra});
function audit(extra){const result=auditV8NativeProfile(input(extra));assert.equal(Object.values(result.budget).reduce((a,b)=>a+b,0),result.counts.ticks);
  assert.equal(result.sourceLines.reduce((n,row)=>n+row.ticks,0),result.budget.project);
  assert.equal(result.unresolvedReasons.reduce((n,row)=>n+row.ticks,0),result.budget.unresolvedNative);return result;}
const reason=(result,name)=>result.unresolvedReasons.find(row=>row.reason===name)?.ticks||0;

test('two inlined source owners within one native function stay separate; leaf budget is conserved',()=>{
  const a=audit();assert.deepEqual(a.budget,{project:2,support:1,unresolvedNative:0,other:1});
  assert.deepEqual(a.sourceLines,[{source:'web-player/native/devices/attiny13a/clki_board.inc',line:20,ticks:1},
    {source:'web-player/native/peripherals/device.c',line:10,ticks:1}]);
  assert.equal(a.exclusiveSubsystemTimeAvailable,false);assert.ok(a.limits.some(s=>s.includes('Whole-process')));
  assert.equal(a.counts.knownNativeGenerations,1);assert.equal(a.counts.knownNativeDisassemblyBlocks,1);
});

test('native PC and function-relative source positions use the metadata code offset before source-map lookup',()=>{
  const result=audit({log:creation()+'\n'+tick()});assert.equal(result.budget.project,1);
  const wrong=audit({log:creation()+'\n'+tick(),sourceMap:makeMap([[4,0,9,0]])});
  assert.equal(wrong.budget.project,0);assert.equal(reason(wrong,'source-map-function-gap'),1);
});

test('output and malformed-input errors never echo raw addresses, names or private path prefixes',()=>{
  const text=JSON.stringify(audit());for(const value of ['confidential','0x1000','native.device.service','D:/','C:/'])assert.ok(!text.includes(value));
  assert.throws(()=>audit({functions:[{...fn,name:'native.confidential/name'}]}),error=>!error.message.includes('confidential'));
});

test('path normalization accepts project-internal parent segments but rejects escape and external paths',()=>{
  for(const source of ['C:/private/web-player/native/../../outside.c','D:/private/lib.c','web-player/native/../outside.c',
    'C:/private/not-web-player/native/trick.c','web-player/native/secret?query.c']){
    const a=audit({log:creation()+'\n'+tick(),sourceMap:makeMap([[104,0,0,0]],[source])});assert.equal(a.budget.support,1,source);
  }
  const map=makeMap([[104,0,4,0]],['peripherals/../device.c']);map.sourceRoot='C:/private/web-player/native';
  const a=audit({log:creation()+'\n'+tick(),sourceMap:map});assert.deepEqual(a.sourceLines,[{source:'web-player/native/device.c',line:5,ticks:1}]);
});

test('unmapped source-map segments stop preceding ownership rather than inheriting it',()=>{
  const map=makeMap([[104,0,9,0],[6]]);
  const a=audit({log:[creation(),tick(),tick('0x1021',30)].join('\n'),sourceMap:map});
  assert.equal(a.budget.project,1);assert.equal(reason(a,'unmapped-source-map'),1);
});

test('mapped segments with optional names and negative source/line deltas are accepted',()=>{
  const map=makeMap([[104,1,9,0,0],[8,-1,-4,2,1]]);map.names=['one','two'];
  const a=audit({log:[creation(),tick(),tick('0x1021',30)].join('\n'),sourceMap:map});
  assert.equal(a.budget.project,2);assert.deepEqual(a.sourceLines.map(row=>row.line),[10,6]);
});

test('native prologue gaps, metadata padding and absent source-position tables stay unresolved',()=>{
  const log=[creation(10,'0x1000',80),tick('0x1002',20),tick('0x1048',30)].join('\n');
  const a=audit({log});assert.equal(reason(a,'native-location-gap'),2);
  const b=audit({log:creation()+'\n'+tick(),disassembly:disassembly({positions:[]})});assert.equal(reason(b,'absent-native-positions'),1);
});

test('function-entry source positions and missing maps are explicitly unresolved',()=>{
  const log=creation()+'\n'+tick();
  assert.equal(reason(audit({log,disassembly:disassembly({positions:[[0,0]]})}),'function-entry-position'),1);
  assert.equal(reason(audit({log,sourceMap:null}),'absent-source-map'),1);
});

test('creation ordering and timestamps prevent attributing a tick to future code',()=>{
  for(const log of [tick()+'\n'+creation(10),creation(30)+'\n'+tick('0x1009',20)]){
    const a=audit({log});assert.deepEqual(a.budget,{project:0,support:0,unresolvedNative:0,other:1});
  }
  assert.equal(reason(audit({log:creation(20)+'\n'+tick()}),'creation-time-tie'),1);
});

test('overlapping or reused address generations are not resolved by choosing the latest name',()=>{
  for(const duplicate of [creation(15),creation(15,'0x1008',20,'unknown-public-function')]){
    const a=audit({log:[creation(),duplicate,tick()].join('\n')});assert.equal(reason(a,'ambiguous-address-generation'),1);
  }
  const a=audit({log:[creation(),creation(30,'0x1008',20,'other'),tick('0x1009',20)].join('\n')});assert.equal(a.budget.project,1);
});

test('missing or duplicate native disassembly remains unresolved',()=>{
  const log=creation()+'\n'+tick();assert.equal(reason(audit({log,disassembly:''}),'missing-disassembly'),1);
  assert.equal(reason(audit({log,disassembly:disassembly()+'\n'+disassembly()}),'ambiguous-disassembly'),1);
  assert.equal(reason(audit({log,disassembly:disassembly({base:'0000000000002000'})}),'missing-disassembly'),1);
});

test('external callbacks and anonymous stack addresses do not become native leaf cost',()=>{
  const log=[creation(),tick('0x1009',20,1),tick('0x9000',30)+',0x1009,0x1021'].join('\n');
  const a=audit({log});assert.deepEqual(a.budget,{project:0,support:0,unresolvedNative:0,other:2});
});

test('unsupported code lifecycle records fail closed before stale address reuse',()=>{
  for(const record of ['code-move,0x1000,0x3000','code-delete,0x1000'])assert.throws(()=>audit({log:creation()+'\n'+record+'\n'+tick()}),/Unsupported code-address lifecycle/);
});

test('source-map versions, shapes, VLQ encodings, field counts, order and references are validated',()=>{
  const bad=[{...makeMap(),version:2},{...makeMap(),mappings:'AAAA;AAAA'},{...makeMap(),sources:[3]},
    {...makeMap(),names:[3]},{...makeMap(),sourceRoot:7},{...makeMap(),mappings:','},
    {...makeMap(),mappings:'?'},{...makeMap(),mappings:'g'},{...makeMap(),mappings:'///////////A'},
    makeMap([[104,0]]),makeMap([[104,0,0]]),makeMap([[104,0,0,0,0,0]]),makeMap([[-1]]),
    makeMap([[104,0,0,0],[0]]),makeMap([[104,0,0,0],[-1]]),makeMap([[104,9,0,0]]),
    makeMap([[104,-1,0,0]]),makeMap([[104,0,-1,0]]),makeMap([[104,0,0,-1]]),makeMap([[104,0,0,0,0]])];
  for(const sourceMap of bad)assert.throws(()=>audit({sourceMap}),/source.map|Source.map/);
});

test('native metadata identity and range validation reject stale or duplicate inputs',()=>{
  for(const functions of [null,[{...fn,index:-1}],[{...fn,codeOffset:200}],[{...fn,end:99}],
    [fn,fn],[fn,{...fn,name:'native.device.other'}],[{...fn,codeOffset:Infinity}]])assert.throws(()=>audit({functions}),/metadata/);
  assert.throws(()=>audit({disassembly:disassembly({index:8})}),/stale/);
  assert.throws(()=>audit({disassembly:disassembly({positions:[[8,100]]})}),/Stale/);
  assert.throws(()=>audit({disassembly:disassembly({positions:[[64,4]]})}),/Stale/);
});

test('malformed native position ordering, row syntax, block headers and truncation reject',()=>{
  for(const positions of [[[8,4],[8,5]],[[32,4],[8,5]]])assert.throws(()=>audit({disassembly:disassembly({positions})}),/Unordered/);
  assert.throws(()=>audit({disassembly:disassembly().replace(' 8 4 statement',' invalid-position-row')}),/Malformed native/);
  assert.throws(()=>audit({disassembly:disassembly().replace('index: 7','index: 7\nindex: 7')}),/Duplicate/);
  assert.throws(()=>audit({disassembly:disassembly().replace('compiler: Liftoff','compiler: Liftoff\ncompiler: TurboFan')}),/Duplicate/);
  assert.throws(()=>audit({disassembly:disassembly().replace('--- End code ---','')}),/Truncated/);
  assert.throws(()=>audit({disassembly:'--- End code ---'}),/Unexpected/);
  assert.throws(()=>audit({disassembly:disassembly().replace('name:','--- WebAssembly code ---\nname:')}),/Nested/);
});

test('malformed log record addresses, timestamp integers and ranges reject without echoing contents',()=>{
  const bad=['code-creation,JS',creation().replace('0x1000','not-an-address'),creation().replace(',10,',',-1,'),
    creation(10,'0xffffffffffffffff',64),creation(10,'0x1000',0),'tick,0x1000,20,9,0x0,0','tick,0x1000,no,0,0x0,0','tick,0x1000'];
  for(const log of bad)assert.throws(()=>audit({log}),/Malformed|Invalid/);
  assert.throws(()=>audit({log:null}),/strings/);assert.throws(()=>audit({disassembly:null}),/strings/);
});

const uleb=value=>{const out=[];do{const b=value%128;value=Math.floor(value/128);out.push(b+(value?128:0));}while(value);return out;};
const utf8=value=>{const bytes=Array.from(new TextEncoder().encode(value));return [...uleb(bytes.length),...bytes];};
const section=(id,payload)=>[id,...uleb(payload.length),...payload];
const functionNames=names=>section(0,[...utf8('name'),...section(1,[...uleb(names.length),...names.flatMap((name,index)=>[...uleb(index),...utf8(name)])])]);
function tinyNative(names=['native.test.first','native.test.second']){
  assert.ok(names.length===1||names.length===2);
  const prefix=[0,97,115,109,1,0,0,0,...section(1,[1,0x60,0,0]),...section(3,[names.length,...names.map(()=>0)])];
  const code=section(10,[names.length,...names.flatMap(()=>[2,0,0x0b])]);
  const first=names.length===1?22:23;
  return {bytes:Uint8Array.from([...prefix,...code,...functionNames(names)]),
    functions:names.map((name,index)=>({name,index,codeOffset:first+index*3,end:first+index*3+2})),prefix,code};
}

test('native metadata binds every name/index/body boundary to one or two actual WASM declarations',()=>{
  for(const names of [['native.test.only'],['native.test.first','native.test.second']]){
    const {functions,bytes}=tinyNative(names);assert.ok(WebAssembly.validate(bytes));
    assert.deepEqual(validateV8NativeFunctions(functions,bytes),{functions:names.length,imports:0,bytes:bytes.length});
  }
});

test('shifted bounds, stale names/indices, missing and extra native metadata reject',()=>{
  const {functions,bytes}=tinyNative();
  for(const altered of [functions.map(f=>({...f,codeOffset:f.codeOffset+16,end:f.end+16})),
    functions.map(f=>({...f,codeOffset:f.codeOffset+1})),functions.map(f=>({...f,end:f.end+1})),
    [{...functions[0],index:1},{...functions[1],index:0}],
    [{...functions[0],name:'native.test.wrong'},functions[1]],functions.slice(0,1),
    [...functions,{name:'native.test.extra',index:2,codeOffset:100,end:110}],
    [...functions,{name:'cpu.other',index:2,codeOffset:100,end:110}]]){
    assert.throws(()=>validateV8NativeFunctions(altered,bytes),/metadata/);
  }
});

test('the last function-name subsection is authoritative while earlier custom metadata stays opaque',()=>{
  const {functions,prefix,code}=tinyNative(),correct=functions.map(f=>f.name);
  const bytes=Uint8Array.from([...prefix,...code,...functionNames(['native.old.first','native.old.second']),...functionNames(correct)]);
  assert.equal(validateV8NativeFunctions(functions,bytes).functions,2);
  const stale=Uint8Array.from([...prefix,...code,...functionNames(correct),...functionNames(['native.old.first','native.old.second'])]);
  assert.throws(()=>validateV8NativeFunctions(functions,stale),/metadata/);
  const missing=Uint8Array.from([...prefix,...code,...functionNames(correct.slice(0,1))]);
  assert.throws(()=>validateV8NativeFunctions(functions,missing),/metadata/);
  const extra=Uint8Array.from([...prefix,...code,...functionNames([...correct,'native.extra.third'])]);
  assert.throws(()=>validateV8NativeFunctions(functions,extra),/metadata/);
});

test('actual custom sections before code cannot be ignored when validating absolute body offsets',()=>{
  const {functions,prefix,code}=tinyNative();
  const bytes=Uint8Array.from([...prefix,...section(0,[...utf8('other'),1,2,3]),...code,...functionNames(functions.map(f=>f.name))]);
  assert.ok(WebAssembly.validate(bytes));assert.throws(()=>validateV8NativeFunctions(functions,bytes),/metadata/);
  const shifted=functions.map(f=>({...f,codeOffset:f.codeOffset+11,end:f.end+11}));
  assert.equal(validateV8NativeFunctions(shifted,bytes).functions,2);
});

test('native WASM imports, invalid executables and truncated/malformed custom names reject generically',()=>{
  const {functions,bytes,prefix,code}=tinyNative();
  const imported=Uint8Array.from([0,97,115,109,1,0,0,0,...section(1,[1,0x60,0,0]),
    ...section(2,[1,...utf8('private-module'),...utf8('private-function'),0,0])]);
  assert.ok(WebAssembly.validate(imported));assert.throws(()=>validateV8NativeFunctions([],imported),/imports/);
  for(const binary of [new Uint8Array(),bytes.subarray(0,bytes.length-1),Uint8Array.from([1,2,3]),
    Uint8Array.from([...prefix,...code,...section(0,[...utf8('name'),1,99,0])]),
    Uint8Array.from([...prefix,...code,...section(0,[...utf8('name'),...section(1,[1,0,99,0])])]),
    Uint8Array.from([...prefix,...code,...section(0,[...utf8('name'),...section(1,[2,0,...utf8('native.one'),0,...utf8('native.two')])])])]){
    assert.throws(()=>validateV8NativeFunctions(functions,binary),error=>!/private-module|private-function/.test(error.message));
  }
  assert.throws(()=>validateV8NativeFunctions(functions,Array.from(bytes)),/Invalid native WASM/);
});
