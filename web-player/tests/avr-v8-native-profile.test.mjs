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
function checkContainers(result){
  const functions=result.nativeFunctions;
  assert.ok(Array.isArray(functions));assert.ok(Number.isSafeInteger(result.uncontainedNativeTicks)&&result.uncontainedNativeTicks>=0);
  assert.deepEqual(functions.map(row=>row.index),[...new Set(functions.map(row=>row.index))].sort((a,b)=>a-b));
  for(const row of functions){
    assert.deepEqual(Object.keys(row).sort(),['budget','index','ticks','unresolvedReasons']);
    assert.ok(Number.isSafeInteger(row.index)&&row.index>=0);
    assert.deepEqual(Object.keys(row.budget),['project','support','unresolvedNative']);
    assert.equal(Object.values(row.budget).reduce((a,b)=>a+b,0),row.ticks);
    assert.equal(row.unresolvedReasons.reduce((n,s)=>n+s.ticks,0),row.budget.unresolvedNative);
  }
  for(const category of ['project','support'])assert.equal(functions.reduce((n,row)=>n+row.budget[category],0),result.budget[category]);
  assert.equal(functions.reduce((n,row)=>n+row.budget.unresolvedNative,0)+result.uncontainedNativeTicks,result.budget.unresolvedNative);
  assert.equal(functions.reduce((n,row)=>n+row.ticks,0)+result.uncontainedNativeTicks,
    result.budget.project+result.budget.support+result.budget.unresolvedNative);
}
function audit(extra){const result=auditV8NativeProfile(input(extra));assert.equal(Object.values(result.budget).reduce((a,b)=>a+b,0),result.counts.ticks);
  assert.equal(result.sourceLines.reduce((n,row)=>n+row.ticks,0),result.budget.project);
  assert.equal(result.unresolvedReasons.reduce((n,row)=>n+row.ticks,0),result.budget.unresolvedNative);checkContainers(result);return result;}
const reason=(result,name)=>result.unresolvedReasons.find(row=>row.reason===name)?.ticks||0;

test('two inlined source owners within one native function stay separate; leaf budget is conserved',()=>{
  const a=audit();assert.deepEqual(a.budget,{project:2,support:1,unresolvedNative:0,other:1});
  assert.deepEqual(a.sourceLines,[{source:'web-player/native/devices/attiny13a/clki_board.inc',line:20,ticks:1},
    {source:'web-player/native/peripherals/device.c',line:10,ticks:1}]);
  assert.equal(a.exclusiveSubsystemTimeAvailable,false);assert.ok(a.limits.some(s=>s.includes('Whole-process')));
  assert.equal(a.counts.knownNativeGenerations,1);assert.equal(a.counts.knownNativeDisassemblyBlocks,1);
  assert.deepEqual(a.nativeFunctions,[{index:7,ticks:3,budget:{project:2,support:1,unresolvedNative:0},unresolvedReasons:[]}]);
  assert.equal(a.uncontainedNativeTicks,0);
});

test('native function containers retain actual prologue bytes but exclude allocation padding and the instruction end',()=>{
  const log=[creation(10,'0x1000',80),...['0x1000','0x1002','0x103f','0x1040','0x1048','0x104f','0x1050'].map((pc,n)=>tick(pc,20+n))].join('\n');
  const a=audit({log});assert.deepEqual(a.budget,{project:0,support:1,unresolvedNative:5,other:1});
  assert.deepEqual(a.nativeFunctions,[{index:7,ticks:3,budget:{project:0,support:1,unresolvedNative:2},
    unresolvedReasons:[{reason:'native-location-gap',ticks:2}]}]);
  assert.equal(a.uncontainedNativeTicks,3);assert.equal(reason(a,'native-location-gap'),5);
});

test('known native containers do not require mapped source positions or source-map ownership',()=>{
  const log=creation()+'\n'+tick();
  for(const extra of [{disassembly:disassembly({positions:[]})},{disassembly:disassembly({positions:[[0,0]]})},
    {sourceMap:null},{sourceMap:makeMap([[104]])},{sourceMap:makeMap([[4,0,9,0]])}]){
    const a=audit({log,...extra});assert.equal(a.nativeFunctions.length,1);assert.equal(a.nativeFunctions[0].index,7);
    assert.equal(a.nativeFunctions[0].budget.unresolvedNative,1);assert.deepEqual(a.nativeFunctions[0].unresolvedReasons,a.unresolvedReasons);
    assert.equal(a.uncontainedNativeTicks,0);assert.deepEqual(a.sourceLines,[]);
  }
});

test('ambiguous generations, creation ties and absent or ambiguous disassembly never produce a native container',()=>{
  const base=creation()+'\n'+tick();
  for(const extra of [{log:creation(20)+'\n'+tick()},{log:[creation(),creation(15),tick()].join('\n')},
    {log:[creation(),creation(15,'0x1008',20,'unknown-public-function'),tick()].join('\n')},
    {disassembly:''},{disassembly:disassembly()+'\n'+disassembly()},
    {disassembly:disassembly({base:'0000000000002000'})}]){
    const a=audit({log:base,...extra});assert.deepEqual(a.nativeFunctions,[]);assert.equal(a.uncontainedNativeTicks,1);
    assert.equal(a.budget.unresolvedNative,1);
  }
});

test('native containers use sorted verified numeric indices and retain separate generation/source budgets',()=>{
  const second={name:'native.private.second',index:2,codeOffset:300,end:400};
  const log=[creation(),creation(10,'0x2000',64,second.name),tick(),tick('0x2009',30),tick('0x2002',40),tick('0x9000',50)].join('\n');
  const a=audit({log,functions:[fn,second],
    disassembly:disassembly()+'\n'+disassembly({name:second.name,index:second.index,base:'0000000000002000'}),
    sourceMap:makeMap([[104,0,9,0],[200,1,10,0]])});
  assert.deepEqual(a.nativeFunctions,[{index:2,ticks:2,budget:{project:1,support:0,unresolvedNative:1},
    unresolvedReasons:[{reason:'native-location-gap',ticks:1}]},
    {index:7,ticks:1,budget:{project:1,support:0,unresolvedNative:0},unresolvedReasons:[]}]);
  const text=JSON.stringify(a.nativeFunctions);
  for(const raw of ['native.','private','0x1000','0x2000','confidential','C:/','D:/','source','name','base','codeOffset'])assert.ok(!text.includes(raw));
});

test('external callbacks and ticks outside native generations do not contribute to container counts',()=>{
  const a=audit({log:[creation(),creation(10,'0x3000',64,'cpu.private.generated'),creation(10,'0x4000',64,'v8.private.stub'),
    tick('0x1009',20,1),tick('0x9000',30),tick('0x1040',40),tick('0x3009',50),tick('0x4009',60)].join('\n')});
  assert.equal(a.budget.other,5);assert.deepEqual(a.nativeFunctions,[]);assert.equal(a.uncontainedNativeTicks,0);
});

test('disjoint tier generations of one verified function aggregate under its numeric index',()=>{
  const log=[creation(),tick(),creation(30,'0x2000'),tick('0x2021',40),tick('0x2031',50),tick('0x2000',60)].join('\n');
  const a=audit({log,disassembly:disassembly()+'\n'+disassembly({base:'0000000000002000',compiler:'TurboFan'})});
  assert.deepEqual(a.nativeFunctions,[{index:7,ticks:4,budget:{project:2,support:1,unresolvedNative:1},
    unresolvedReasons:[{reason:'native-location-gap',ticks:1}]}]);
  assert.equal(a.uncontainedNativeTicks,0);assert.equal(a.counts.knownNativeGenerations,2);
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

const label=n=>'MM_AVR_CAPTURE_'+n;
const marker=(kind,time,n=0)=>`timer-event-${kind},${label(n)},${time}`;
const window=(workWallMs,n=0)=>({label:label(n),workWallMs});
function checkWindows(result){
  const w=result.windowed,views=[w.certainInterior,w.boundary,w.outside];
  assert.equal(views.reduce((n,row)=>n+row.ticks,0),result.counts.ticks);
  for(const category of Object.keys(result.budget))assert.equal(views.reduce((n,row)=>n+row.budget[category],0),result.budget[category]);
  for(const row of [...views,...w.windows.flatMap(win=>[win.certainInterior,win.boundary])]){
    checkContainers(row);
    assert.equal(Object.values(row.budget).reduce((a,b)=>a+b,0),row.ticks);
    assert.equal(row.sourceLines.reduce((n,s)=>n+s.ticks,0),row.budget.project);
    assert.equal(row.unresolvedReasons.reduce((n,s)=>n+s.ticks,0),row.budget.unresolvedNative);
  }
  assert.equal(w.windows.reduce((n,win)=>n+win.certainInterior.ticks,0),w.certainInterior.ticks);
  assert.equal(w.windows.reduce((n,win)=>n+win.boundary.ticks,0),w.boundary.ticks);
  assert.equal(views.reduce((n,row)=>n+row.uncontainedNativeTicks,0),result.uncontainedNativeTicks);
  for(const fn of result.nativeFunctions)for(const category of Object.keys(fn.budget))assert.equal(
    views.reduce((n,row)=>n+(row.nativeFunctions.find(candidate=>candidate.index===fn.index)?.budget[category]||0),0),fn.budget[category]);
}

test('absent window requests preserve the entire whole-process result and ignore unrelated or reserved timers',()=>{
  const original=audit(),timers=['timer-event-start,ordinary-private-timer,bad',marker('start',10),
    marker('start',20),'timer-event-end,MM_AVR_CAPTURE_unknown,invalid'];
  const actual=audit({log:timers.join('\n')+'\n'+input().log});assert.deepEqual(actual,original);
  assert.ok(!Object.hasOwn(actual,'windowed'));
});

test('window views conserve native candidates inside and outside, with ties kept in conservative boundary bands',()=>{
  const ticks=[99,100,105,106,107,193,194,199,200].map(time=>tick('0x1009',time));
  ticks.push(tick('0x1002',120),tick('0x1031',130),tick('0x9000',140));
  const log=[creation(),marker('start',100),...ticks,marker('end',200)].join('\n');
  const a=audit({log,windows:[window(0.096)]});checkWindows(a);
  assert.deepEqual(a.budget,{project:9,support:1,unresolvedNative:1,other:1});
  assert.deepEqual(a.windowed.certainInterior.budget,{project:2,support:1,unresolvedNative:1,other:1});
  assert.equal(a.windowed.boundary.ticks,5);assert.equal(a.windowed.outside.ticks,2);
  assert.deepEqual(a.windowed.windows.map(({label,outerDurationUs,innerDurationUs,boundaryAllowanceUs})=>
    ({label,outerDurationUs,innerDurationUs,boundaryAllowanceUs})),[{label:label(0),outerDurationUs:100,innerDurationUs:96,boundaryAllowanceUs:6}]);
  assert.equal(a.windowed.certainInterior.sourceLines[0].ticks,2);assert.equal(a.windowed.outside.sourceLines[0].ticks,2);
  const text=JSON.stringify(a);for(const privateValue of ['confidential','0x1009','0x1000','C:/'])assert.ok(!text.includes(privateValue));
  assert.ok(!Object.hasOwn(a.windowed.windows[0],'start'));assert.ok(!Object.hasOwn(a.windowed.windows[0],'end'));
});

test('window views separately conserve multiple function budgets and native padding without containers',()=>{
  const second={name:'native.private.second',index:2,codeOffset:300,end:400};
  const log=[creation(10,'0x1000',80),creation(10,'0x2000',64,second.name),marker('start',100),
    tick('0x1009',99),tick('0x1040',100),tick('0x2002',110),tick('0x1009',120),tick('0x1031',130),
    tick('0x2009',194),tick('0x1048',200),tick('0x9000',210),marker('end',200)].join('\n');
  const a=audit({log,functions:[fn,second],windows:[window(0.096)],
    disassembly:disassembly()+'\n'+disassembly({name:second.name,index:second.index,base:'0000000000002000'}),
    sourceMap:makeMap([[104,0,9,0],[8,1,10,0],[8,1,0,0],[184,-2,5,0]])});checkWindows(a);
  assert.deepEqual(a.budget,{project:3,support:1,unresolvedNative:3,other:1});assert.equal(a.uncontainedNativeTicks,2);
  const {certainInterior,boundary,outside}=a.windowed;
  assert.deepEqual(certainInterior.budget,{project:1,support:1,unresolvedNative:1,other:0});
  assert.deepEqual(boundary.budget,{project:1,support:0,unresolvedNative:1,other:0});
  assert.deepEqual(outside.budget,{project:1,support:0,unresolvedNative:1,other:1});
  assert.deepEqual([certainInterior,boundary,outside].map(row=>row.uncontainedNativeTicks),[0,1,1]);
  assert.deepEqual(certainInterior.nativeFunctions.map(row=>row.index),[2,7]);
  assert.equal(certainInterior.nativeFunctions[0].budget.unresolvedNative,1);
});

test('zero and tiny marker intervals allow an empty certain interior without fabricating attribution',()=>{
  for(let duration=0;duration<=4;duration++){
    const log=[creation(),marker('start',100),...Array.from({length:duration+2},(_,n)=>tick('0x1009',99+n)),marker('end',100+duration)].join('\n');
    const a=audit({log,windows:[window(duration/1000)]});checkWindows(a);
    assert.equal(a.windowed.certainInterior.ticks,0);assert.deepEqual(a.windowed.certainInterior.sourceLines,[]);
    assert.equal(a.windowed.boundary.ticks,duration);assert.equal(a.windowed.outside.ticks,2);
    assert.equal(a.windowed.windows[0].boundaryAllowanceUs,2);
  }
  const a=audit({log:[marker('start',100),marker('end',100)].join('\n'),windows:[window(0.002)]});checkWindows(a);
  assert.equal(a.counts.ticks,0);assert.equal(a.windowed.windows[0].boundaryAllowanceUs,2);
});

test('adjacent windows own shared boundary ticks once and request order does not change chronology',()=>{
  const log=[creation(),marker('start',100),tick('0x1009',110),marker('end',120),marker('start',120,1),
    tick('0x1009',120),tick('0x1009',130),marker('end',140,1),tick('0x1009',140)].join('\n');
  const a=audit({log,windows:[window(0.020,1),window(0.020)]});checkWindows(a);
  assert.equal(a.windowed.certainInterior.ticks,2);assert.equal(a.windowed.boundary.ticks,1);assert.equal(a.windowed.outside.ticks,1);
  assert.deepEqual(a.windowed.windows.map(w=>w.label),[label(0),label(1)]);
  assert.equal(a.windowed.windows[0].boundary.ticks,0);assert.equal(a.windowed.windows[1].boundary.ticks,1);
});

test('zero-duration adjacent windows sort by marker order when timestamps coincide',()=>{
  const log=[creation(),marker('start',100),marker('end',100),marker('start',100,1),tick('0x1009',110),marker('end',120,1)].join('\n');
  const a=audit({log,windows:[window(0.020,1),window(0)]});checkWindows(a);
  assert.deepEqual(a.windowed.windows.map(w=>w.label),[label(0),label(1)]);assert.equal(a.windowed.certainInterior.ticks,1);
});

test('requested labels and work durations reject malformed, duplicate and unsafe values without echoing them',()=>{
  const invalid=[null,{},[null],[{}],[window(-1)],[window(NaN)],[window(Infinity)],[window(Number.MAX_VALUE)],
    [{label:label(0),workWallMs:'1'}],[{label:'MM_AVR_CAPTURE_private',workWallMs:0}],
    [{label:'MM_AVR_CAPTURE_00',workWallMs:0}],[{label:'MM_AVR_CAPTURE_9007199254740992',workWallMs:0}],[window(1),window(1)]];
  for(const windows of invalid)assert.throws(()=>audit({windows}),error=>/Window|window/.test(error.message)&&!error.message.includes('private'));
});

test('requested marker pairs reject missing, duplicate, malformed and reversed records',()=>{
  const bad=['',marker('start',100),marker('end',200),[marker('end',200),marker('start',100)].join('\n'),
    [marker('start',200),marker('end',100)].join('\n'),[marker('start',100),marker('start',100),marker('end',200)].join('\n'),
    [marker('start',100),marker('end',200),marker('end',200)].join('\n'),
    [marker('start',100)+',extra',marker('end',200)].join('\n'),[marker('start','bad'),marker('end',200)].join('\n'),
    [marker('start',-1),marker('end',200)].join('\n'),[marker('start',100),marker('end','9007199254740992')].join('\n')];
  for(const log of bad)assert.throws(()=>audit({log,windows:[window(0)]}),/window|Window/);
});

test('reserved timer names must be requested while unrelated timers remain ignored',()=>{
  const valid=[marker('start',100),marker('end',200)].join('\n');
  for(const extra of [marker('start',100,1),'timer-event-start,MM_AVR_CAPTURE_private,100',
    'timer-event,MM_AVR_CAPTURE_0,110'])assert.throws(()=>audit({log:valid+'\n'+extra,windows:[window(0)]}),/window/);
  const a=audit({log:'timer-event-start,unrelated-confidential-name,bad\n'+valid,windows:[window(0)]});checkWindows(a);
  assert.ok(!JSON.stringify(a).includes('confidential'));
  const empty=audit({windows:[]});checkWindows(empty);assert.equal(empty.windowed.outside.ticks,empty.counts.ticks);
});

test('nested, crossing and timestamp-overlapping windows reject even when an interval is empty',()=>{
  const logs=[
    [marker('start',100),marker('start',120,1),marker('end',150,1),marker('end',200)],
    [marker('start',100),marker('start',120,1),marker('end',200),marker('end',220,1)],
    [marker('start',100),marker('end',200),marker('start',150,1),marker('end',250,1)],
    [marker('start',100),marker('start',120,1),marker('end',120,1),marker('end',200)],
    [marker('start',100),marker('end',200),marker('start',150,1),marker('end',150,1)],
  ];
  for(const rows of logs)assert.throws(()=>audit({log:rows.join('\n'),windows:[window(0),window(0,1)]}),/window/);
});

test('logger rounding permits exactly two microseconds of inner/outer disagreement and pads fractional overhead conservatively',()=>{
  const log=[marker('start',100),marker('end',110)].join('\n');
  const a=audit({log,windows:[window(0.012)]});checkWindows(a);assert.equal(a.windowed.windows[0].boundaryAllowanceUs,2);
  assert.throws(()=>audit({log,windows:[window(0.012001)]}),/Inconsistent window clock/);
  const b=audit({log,windows:[window(0.0071)]});assert.equal(b.windowed.windows[0].boundaryAllowanceUs,5);
});

test('logged window chronology rejects a native clock rollback rather than sorting it away',()=>{
  const log=[marker('start',100),marker('end',200),marker('start',0,1),marker('end',50,1)].join('\n');
  for(const windows of [[window(0.100),window(0.050,1)],[window(0.050,1),window(0.100)]])
    assert.throws(()=>audit({log,windows}),/Overlapping window intervals/);
});
