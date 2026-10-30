// Diagnostic source-entry counts and a bounded chronological prefix.
// Only ignored build copies are instrumented; no production file is edited.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,cpSync,readdirSync,existsSync} from 'node:fs';
import {resolve,dirname,join,parse} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {spawnSync,execFileSync} from 'node:child_process';
import {parseArgs} from 'node:util';
import {ATtiny13A} from '../lib/attiny13a-runtime.js';
import {parseHex} from '../lib/hex.js';
import {avr,IO,flash} from '../tests/fixtures/attiny13a-system-firmware.mjs';
import {AT13_MASK as MASK} from '../lib/attiny13a-registers.js';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{'out-dir':{type:'string',default:'build/traces/current'},emsdk:{type:'string'},
  'physical-firmware':{type:'boolean',default:false},'eager-collector':{type:'boolean',default:false},
  'full-publication':{type:'boolean',default:false},'gpio-full-dispatch':{type:'boolean',default:false},
  'deadline-counters':{type:'boolean',default:false}}});
const out=resolve(root,values['out-dir']),native=join(out,'native');mkdirSync(out,{recursive:true});
const sha=b=>createHash('sha256').update(b).digest('hex');
const source=p=>readFileSync(resolve(root,p),'utf8').replaceAll('\r\n','\n');
const manifest=JSON.parse(source('web-player/wasm/device-build.json'));
const production=readFileSync(resolve(root,'web-player/wasm/attiny13a.wasm'));
assert.equal(sha(production),manifest.artifacts['attiny13a.wasm']);
for(const [path,expected] of Object.entries(manifest.inputs))assert.equal(sha(source(path)),expected,path);
cpSync(resolve(root,'web-player/native'),native,{recursive:true,filter:path=>
  !/\.[^/\\]+$/.test(path)||/\.(?:c|h|inc)$/.test(path)});
const selected={
  'peripherals/device.c':['next_event','next_event_scan','advance_to','elapse','service','service_clocks',
    'service_async','service_end','mirror','ratio','rational','duration','capture_pins','pin_voltages','timer_outputs',
    'sources','clock_domains','wake','device_pending_irqs','device_next_cpu_event','advance_half_until_ps'],
  'devices/attiny13a/clki_board.inc':['clki_service','clki_refill','clki_next_edge','clki_source_rise','clki_wake'],
  'avr-device.inc':['full_clock','full_deadline','full_audio_collect','avr_device_phase_clock',
    'avr_device_phase_retire','full_interrupt'],
  'peripherals/analog.c':['analog_advance','analog_input','analog_sources','analog_next_event','connect_sources'],
  'peripherals/analog_adc.c':['analog_adc_advance','analog_adc_input','analog_adc_sources','analog_adc_next_event'],
  'peripherals/analog_comparator.c':['analog_comparator_advance','analog_comparator_input','analog_comparator_next_event'],
  'peripherals/timer0.c':['timer0_advance','timer0_next_event'],
  'peripherals/system_gpio.c':['system_gpio_external','system_gpio_clock','system_gpio_advance','system_gpio_settled','system_gpio_next_event_half'],
  'peripherals/system_sleep.c':['system_sleep_advance','system_sleep_clock_edge','system_sleep_domains'],
  'peripherals/nvm.c':['nvm_advance','nvm_next_event_cycle','nvm_next_event_ns'],
  'peripherals/system_watchdog.c':['system_watchdog_advance','system_watchdog_until_timeout'],
  'devices/attiny13a/clki_input.c':['attiny13a_clki_enqueue','attiny13a_clki_peek','attiny13a_clki_consume','attiny13a_clki_hold_until'],
  'devices/attiny13a/clki_clock.c':['attiny13a_clki_clock_edge'],
  'devices/attiny13a/clki_periodic.c':['attiny13a_clki_periodic_peek','attiny13a_clki_periodic_consume'],
};
// Optional candidate helper: the function table records its presence explicitly.
if(source('web-player/native/peripherals/device.c').includes('static void watchdog_sync('))
  selected['peripherals/device.c'].push('watchdog_sync');
for(const helper of ['mirror_configuration','mirror_dynamic'])
  if(source('web-player/native/peripherals/device.c').includes('static void '+helper+'('))
    selected['peripherals/device.c'].push(helper);
const functions=[];
const deadline=!!values['deadline-counters'];
const deviceSource=source('web-player/native/peripherals/device.c');
const reasonEnums=deadline?[...deviceSource.matchAll(/enum deadline_reason\s*\{([^}]+)\}/g)]:[];
if(deadline)assert.equal(reasonEnums.length,1,'One original deadline-reason enum required');
const reasons=deadline?reasonEnums[0][1].split(',').map(s=>s.trim()).filter(Boolean):[];
assert.ok(reasons.length<32&&reasons.every(s=>/^DEADLINE_[A-Z_]+$/.test(s)));
if(deadline)selected['peripherals/device.c'].push('deadline_invalidate','at_half','at_cycle','after_units');
const probe=(name,kind='deadline-outcome')=>{
  const id=functions.length;functions.push({id,name,source:'web-player/native/peripherals/device.c',kind});return id;
};
for(const [file,names] of Object.entries(selected)){
  let text=readFileSync(join(native,file),'utf8');
  for(const name of names){
    const id=functions.length,pattern=new RegExp('(^[^(){};]*\\b'+name+'\\s*\\([^;{}]*\\)\\s*\\{)','gm');
    const matches=[...text.matchAll(pattern)];assert.equal(matches.length,1,file+': '+name+' definition');
    functions.push({id,name,source:'web-player/native/'+file,kind:'function-entry'});
    let hits=' MM_TRACE_HIT('+id+');';
    if(deadline&&name==='next_event_scan'){
      const exit=probe('next_event_scan:exit');
      const body=/(static uint64_t next_event_scan\(void\)\s*\{)([\s\S]*?)(\n\})/g;
      const matches=[...text.matchAll(body)];assert.equal(matches.length,1,'One scanner body required');
      assert.equal((matches[0][2].replace(/\/\*[\s\S]*?\*\//g,'').match(/\breturn\b/g)||[]).length,1,
        'Scanner instrumentation requires its single original return');
      assert.equal((matches[0][2].match(/\breturn next;/g)||[]).length,1);
      text=text.replace(body,(_,start,code,end)=>start+code.replace(/\breturn next;/,
        `--mm_trace_scan_level; MM_TRACE_HIT(${exit}); return next;`)+end);
      hits+=' ++mm_trace_scan_level;';
    }
    if(deadline&&name==='duration'){
      const inside=probe('duration:scan'),outside=probe('duration:outside-scan');
      hits+=` if(mm_trace_scan_level) { MM_TRACE_HIT(${inside}); } else { MM_TRACE_HIT(${outside}); }`;
    }
    if(deadline&&name==='deadline_invalidate'){
      const attempts=reasons.map(s=>probe('invalidate:'+s,'deadline-invalidation-attempt'));
      const valid=reasons.map(s=>probe('invalidate-valid:'+s,'deadline-valid-invalidation'));
      hits+=` MM_TRACE_HIT(${attempts[0]}+reason);
        if(board.deadline.valid) { MM_TRACE_HIT(${valid[0]}+reason); }
        mm_trace_deadline_pending|=UINT32_C(1)<<reason;`;
    }
    if(deadline&&name==='next_event'){
      const hit=probe('next_event:hit'),miss=probe('next_event:miss'),none=probe('miss:no-pending-reason');
      const pending=reasons.map(s=>probe('miss:'+s,'deadline-miss-reason'));
      hits+=` if(board.deadline.valid&&board.deadline.base==board.base) { MM_TRACE_HIT(${hit}); }
        else { MM_TRACE_HIT(${miss});
          if(!mm_trace_deadline_pending) { MM_TRACE_HIT(${none}); }
          for(unsigned n=0;n<${reasons.length};n++)if(mm_trace_deadline_pending&(UINT32_C(1)<<n)) { MM_TRACE_HIT(${pending[0]}+n); }
          mm_trace_deadline_pending=0;
        }`;
    }
    if(deadline&&name==='at_half'){
      const ids=['never','due','unknown-clki','convert'].map(s=>probe('at_half:'+s));
      const scan=probe('at_half:scan'),convert=probe('at_half:scan-convert');
      hits+=` if(mm_trace_scan_level) { MM_TRACE_HIT(${scan});
        if(half!=UINT64_MAX&&half>board.half&&!board.clki_enabled) { MM_TRACE_HIT(${convert}); } }`;
      hits+=` if(half==UINT64_MAX) { MM_TRACE_HIT(${ids[0]}); }
        else if(half<=board.half) { MM_TRACE_HIT(${ids[1]}); }
        else if(board.clki_enabled) { MM_TRACE_HIT(${ids[2]}); }
        else { MM_TRACE_HIT(${ids[3]}); }`;
    }
    if(deadline&&name==='elapse'){
      const ids=['zero','positive','backwards'].map(s=>probe('elapse:'+s));
      const future=probe('elapse:zero-cached-future');
      hits+=` if(target==board.base&&board.deadline.valid&&board.deadline.base==board.base&&board.deadline.at>board.base) { MM_TRACE_HIT(${future}); }`;
      hits+=` if(target==board.base) { MM_TRACE_HIT(${ids[0]}); }
        else if(target>board.base) { MM_TRACE_HIT(${ids[1]}); }
        else { MM_TRACE_HIT(${ids[2]}); }`;
    }
    if(name==='analog_adc_advance'){
      const states=['disabled','enabled-idle','converting','clock-gated'];
      const ids=states.map(state=>{
        const next=functions.length;
        functions.push({id:next,name:name+':'+state,source:'web-player/native/'+file,kind:'adc-state-entry'});
        return next;
      });
      hits+=` if(!(adc->adcsra&ANALOG_ADEN)) { MM_TRACE_HIT(${ids[0]}); }
        else if(adc->phase==IDLE) { MM_TRACE_HIT(${ids[1]}); }
        else { MM_TRACE_HIT(${ids[2]}); }
        if(!adc->clock_running) { MM_TRACE_HIT(${ids[3]}); }`;
    }
    text=text.replace(pattern,'$1'+hits);
  }
  writeFileSync(join(native,file),text);
}
if(values['eager-collector']){
  const file=join(native,'peripherals/device.c'),text=readFileSync(file,'utf8'),
    pattern=/int device_pin_buffer_ready\(void\)\s*\{[^{}]*\}/g;
  assert.equal([...text.matchAll(pattern)].length,1,'Independent native PCM pressure query');
  writeFileSync(file,text.replace(pattern,'int device_pin_buffer_ready(void) { return 1; }'));
}
const diagHeader=join(out,'trace-counters.h');
writeFileSync(diagHeader,`#include <stdint.h>
extern uint64_t mm_trace_counts[${functions.length}];
extern uint32_t mm_trace_length;
extern uint32_t mm_trace_deadline_pending;
extern uint32_t mm_trace_scan_level;
void mm_trace_record(uint32_t id);
#define MM_TRACE_HIT(id) do { ++mm_trace_counts[id]; if(mm_trace_length<256)mm_trace_record(id); } while(0)
`);
const diagSource=join(out,'trace-counters.c');
writeFileSync(diagSource,`#include "trace-counters.h"
#include "native/peripherals/device.h"
uint64_t mm_trace_counts[${functions.length}];
uint32_t mm_trace_length;
uint32_t mm_trace_deadline_pending;
uint32_t mm_trace_scan_level;
typedef struct {uint64_t sequence,time,half;uint32_t id,reserved;} trace_entry_t;
static trace_entry_t entries[256];
void mm_trace_record(uint32_t id){
 entries[mm_trace_length]=(trace_entry_t){mm_trace_length,
  device_physical_mode()?device_time_ps():device_base_half(),device_virtual_half(),id,0};
 ++mm_trace_length;
}
void mm_trace_clear(void){for(unsigned n=0;n<${functions.length};n++)mm_trace_counts[n]=0;mm_trace_length=0;mm_trace_deadline_pending=0;mm_trace_scan_level=0;}
uint64_t mm_trace_count(uint32_t id){return id<${functions.length}?mm_trace_counts[id]:0;}
uintptr_t mm_trace_buffer(void){return (uintptr_t)entries;}
uint32_t mm_trace_size(void){return mm_trace_length;}
`);
let sdk=values.emsdk||process.env.EMSDK;
for(let parent=root;!sdk;parent=dirname(parent)){
  const candidate=join(parent,'build/toolchains/emscripten-6.0.12');
  if(existsSync(join(candidate,'upstream/bin/clang.exe')))sdk=candidate;
  if(parent===parse(parent).root)break;
}
assert.ok(sdk,'Prepared SDK required');sdk=resolve(sdk);
const compiler=join(sdk,'upstream/bin',process.platform==='win32'?'clang.exe':'clang');
const target=join(out,'runtime-counted.wasm');
const args=[...manifest.flags.map(flag=>flag.replaceAll('<emsdk>',sdk)),
  ...(values['gpio-full-dispatch']?['-DDEVICE_GPIO_IDLE_CACHE=0']:[]),'-include',diagHeader,
  '-I',resolve(root,'web-player/native'),
  ...manifest.sources.map(path=>join(native,path.replace('web-player/native/',''))),diagSource,
  '-Wl,--export=mm_trace_clear','-Wl,--export=mm_trace_count','-Wl,--export=mm_trace_buffer','-Wl,--export=mm_trace_size',
  '-lc','-lclang_rt.builtins','-o',target];
const build=spawnSync(compiler,args,{cwd:root,encoding:'utf8'});
assert.equal(build.status,0,build.stderr||String(build.error));
const countedBytes=readFileSync(target),countedModule=new WebAssembly.Module(countedBytes);
const productionModule=new WebAssembly.Module(production);
assert.deepEqual(WebAssembly.Module.imports(countedModule),[]);
const program=flash({instructions:[avr.ldi(16,1),avr.ldi(17,0x55),avr.add(18,16),
  avr.eor(19,17),avr.inc(20),avr.rjmp(5,2)]});
const catalogPaths=['web-player/firmware.json','web-player/hq4-firmware.json'];
const catalogs=catalogPaths.map(path=>JSON.parse(source(path))),catalog=catalogs.flatMap(row=>row.entries);
const aliases=Object.assign({},...catalogs.map(row=>row.aliases));
const cases=['rhythmic','lumiere-stereo','hq4-chego-auto'].map(id=>{
  const entry=catalog.find(entry=>entry.id===(aliases[id]??id));assert.ok(entry,id);
  assert.equal(sha(parseHex(entry.flashHex)),entry.flashSha256);
  const hz=entry.cpuHz||9600000,calibration=Array(128).fill(0);calibration[0]=hz;
  return{id:id+(values['physical-firmware']?'-physical':''),requestedFirmwareId:id,firmwareId:entry.id,binary:parseHex(entry.flashHex),
    eeprom:entry.eepromHex?parseHex(entry.eepromHex,64):null,
    frames:12000,channels:entry.audioChannels||1,options:{oscillatorHz:hz,fastIdle:true,
      ...values['physical-firmware']?{resumable:true,osccalHz:calibration,
        nvmClockProfile:1,nvmCalibrationReferenceHz:hz}:{}}};
});
assert.equal(new Set(cases.map(entry=>entry.firmwareId)).size,cases.length,'Duplicate resolved firmware');
for(const divisor of [1,256])cases.push({id:'kernel-clki-20m-div'+divisor,binary:program,frames:1200,channels:1,divisor,
  options:{oscillatorHz:20000000,resumable:true,fastIdle:false,fuseLow:0x70,
    clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}});
for(const adcState of ['enabled-idle','converting'])cases.push({
  ...cases.find(row=>row.id==='kernel-clki-20m-div1'),id:'kernel-clki-20m-div1-adc-'+adcState,adcState});
if(deadline)for(const adcState of [undefined,'converting']){
  const calibration=Array(128).fill(0);calibration[0]=20000000;
  cases.push({id:'kernel-internal-20m-direct'+(adcState?'-adc-converting':''),binary:program,channels:1,
    instructions:1000000,adcState,options:{oscillatorHz:20000000,resumable:true,fastIdle:false,
      fuseLow:0x72,osccalHz:calibration}});
}
function make(entry,runtimeModule){
  const c=new ATtiny13A(entry.binary,entry.eeprom,{...entry.options,runtimeModule,
    optimizeIOPublication:!values['full-publication']});
  if(entry.adcState){c.writeIO(IO.ADMUX,3);c.writeIO(IO.ADCSRA,entry.adcState==='converting'?0xe7:MASK.ADEN);}
  if(entry.divisor){
    c.writeIO(IO.CLKPR,128);c.writeIO(IO.CLKPR,Math.log2(entry.divisor));
    const end=BigInt(entry.frames)*1000000000000n/48000n;
    assert.equal(c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:25000n,lowPs:25000n,
      transitionCount:end/25000n,knownUntilPs:end}),true);
  }
  return c;
}
function capture(c,entry){
  if(entry.instructions){assert.equal(c.run(entry.instructions),entry.instructions);return Buffer.alloc(0);}
  const blocks=[];
  for(let offset=0;offset<entry.frames;offset+=1024){
    const block=c.capturePhysical(Math.min(1024,entry.frames-offset),48000,entry.channels);
    blocks.push(Buffer.from(block.buffer,block.byteOffset,block.byteLength));
  }
  return Buffer.concat(blocks);
}
const stringify=v=>JSON.stringify(v,(_,v)=>typeof v==='bigint'?v.toString():v,2)+'\n';
const report={schema:'micromusic-native-call-trace-v1',createdAt:new Date().toISOString(),
  policy:{physicalFirmware:values['physical-firmware'],eagerCollector:values['eager-collector'],fullPublication:values['full-publication'],gpioFullDispatch:values['gpio-full-dispatch'],
    deadlineCounters:deadline,
    description:'Optional eager collection forces the copied PCM pressure query true. GPIO full dispatch defines DEVICE_GPIO_IDLE_CACHE=0 only for the counted build; production remains the correctness reference. Counters never establish production elapsed time.'},
  git:{head:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim()},
  productionRuntimeSha256:sha(production),countedRuntimeSha256:sha(countedBytes),
  sourceSha256NormalizedLF:{...Object.fromEntries(Object.keys(manifest.inputs).map(p=>[p,sha(source(p))])),
    ...Object.fromEntries([...catalogPaths,'web-player/scripts/trace-device-calls.mjs',
      'web-player/lib/attiny13a-runtime.js','web-player/lib/avr-transpiled-runtime.js','web-player/lib/avr-transpiler.js','web-player/lib/attiny13a-registers.js',
      'web-player/tests/fixtures/attiny13a-system-firmware.mjs'].map(p=>[p,sha(source(p))]))},
  functions,method:'Counters and first256 chronological source-level function entries in an ignored diagnostic build. Includes entries later inlined by O3, not a WASM call count. Constructors and input submission are excluded; counters reset immediately before capture. Integer board time is ps for CLKI and oscillator half ticks for compatible firmware. No host timestamps or per-edge JS callbacks. Instrumentation changes executable code, layout and performance: its times are never used as production performance or sampling percentages. Final full public/data/Flash/EEPROM/IRQ state and raw PCM must match an uninstrumented production reference.',results:[]};
for(const entry of cases){
  const original=make(entry,productionModule),counted=make(entry,countedModule);
  const expected=capture(original,entry),e=counted._exports;e.mm_trace_clear();
  const actual=capture(counted,entry);
  const counts=functions.map(fn=>({...fn,count:BigInt.asUintN(64,e.mm_trace_count(fn.id)).toString()}));
  const prefix=[],view=new DataView(e.memory.buffer,e.mm_trace_buffer(),e.mm_trace_size()*32);
  for(let n=0;n<e.mm_trace_size();n++)prefix.push({sequence:Number(view.getBigUint64(n*32,true)),
    time:view.getBigUint64(n*32+8,true).toString(),cpuHalf:view.getBigUint64(n*32+16,true).toString(),
    function:functions[view.getUint32(n*32+24,true)].name});
  assert.ok(actual.equals(expected),entry.id+' PCM');
  assert.deepEqual(counted.state(),original.state(),entry.id+' public state');
  assert.equal(counted.state().deviceFault,0,entry.id+' device fault');
  assert.deepEqual(counted._state,original._state,entry.id+' full diagnostics');
  for(const name of ['data','rom','eeprom'])assert.deepEqual(counted[name],original[name],entry.id+' '+name);
  assert.deepEqual(counted.irqFrames,original.irqFrames);
  const physical=!!entry.options.resumable;
  const expectedPins=physical?original.drainPinsPs():original.drainPins(),
    actualPins=physical?counted.drainPinsPs():counted.drainPins();
  assert.deepEqual(actualPins,expectedPins,entry.id+' pin history');
  const entries=name=>BigInt(counts.find(row=>row.name===name).count);
  const adcActivity=Object.fromEntries(['disabled','enabled-idle','converting','clock-gated']
    .map(state=>[state,entries('analog_adc_advance:'+state).toString()]));
  assert.equal(BigInt(adcActivity.disabled)+BigInt(adcActivity['enabled-idle'])+BigInt(adcActivity.converting),entries('analog_adc_advance'));
  assert.ok(BigInt(adcActivity['clock-gated'])<=entries('analog_adc_advance'));
  if(entry.adcState==='enabled-idle'){
    assert.ok(entries('analog_advance')>0n);assert.equal(adcActivity.converting,'0');
    assert.equal(counted.data[32+IO.ADCSRA]&(MASK.ADEN|MASK.ADSC),MASK.ADEN);
  }
  if(entry.adcState==='converting'){assert.ok(BigInt(adcActivity.converting)>0n);assert.ok(counted.data[32+IO.ADCSRA]&MASK.ADIF);}
  const row={id:entry.id,frames:entry.frames,sampleRate:48000,channels:entry.channels,adcActivity,adcState:entry.adcState,
    ...(entry.instructions?{operation:'direct',instructions:entry.instructions}:{operation:'capture'}),
    requestedFirmwareId:entry.requestedFirmwareId,firmwareId:entry.firmwareId,flashSha256:sha(entry.binary),
    timeUnits:physical?'picoseconds':'oscillator half ticks',divisor:entry.divisor??1,
    cycles:counted.cyc,productionEquality:true,rawPcmSha256:sha(actual),pinSha256:sha(stringify(actualPins)),counts,prefix};
  if(deadline){
    assert.equal(entries('next_event:hit')+entries('next_event:miss'),entries('next_event'));
    assert.equal(entries('next_event:miss'),entries('next_event_scan'));
    assert.equal(entries('next_event_scan:exit'),entries('next_event_scan'));
    assert.equal(entries('duration:scan')+entries('duration:outside-scan'),entries('duration'));
    assert.ok(entries('at_half:scan')<=entries('at_half'));
    assert.ok(entries('at_half:scan-convert')<=entries('at_half:convert'));
    assert.equal(reasons.reduce((n,s)=>n+entries('invalidate:'+s),0n),entries('deadline_invalidate'));
    assert.equal(['never','due','unknown-clki','convert'].reduce((n,s)=>n+entries('at_half:'+s),0n),entries('at_half'));
    assert.equal(['zero','positive','backwards'].reduce((n,s)=>n+entries('elapse:'+s),0n),entries('elapse'));
    assert.equal(entries('elapse:backwards'),0n);
    assert.ok(entries('elapse:zero-cached-future')<=entries('elapse:zero'));
    for(const reason of reasons){assert.ok(entries('invalidate-valid:'+reason)<=entries('invalidate:'+reason));
      assert.ok(entries('miss:'+reason)<=entries('next_event:miss'));}
    assert.ok(entries('miss:no-pending-reason')+reasons.reduce((n,s)=>n+entries('miss:'+s),0n)>=entries('next_event:miss'));
    row.deadline={queries:entries('next_event').toString(),hits:entries('next_event:hit').toString(),
      misses:entries('next_event:miss').toString(),noPendingReason:entries('miss:no-pending-reason').toString(),
      scanDurationCalls:entries('duration:scan').toString(),outsideScanDurationCalls:entries('duration:outside-scan').toString(),
      zeroElapseCachedFuture:entries('elapse:zero-cached-future').toString(),
      reasons:reasons.map(s=>({reason:s,attempts:entries('invalidate:'+s).toString(),
        validInvalidations:entries('invalidate-valid:'+s).toString(),missesWithReason:entries('miss:'+s).toString()})),
      missReasonsOverlap:true,counterResetClearsPendingReasons:true};
  }
  report.results.push(row);console.log(entry.id,JSON.stringify(counts.filter(r=>[
    'clki_service','pin_voltages','analog_input','analog_adc_advance','next_event_scan','mirror'].includes(r.name))));
}
report.complete=true;writeFileSync(join(out,'summary.json'),stringify(report));
console.log('All source-entry counter/trace cases match production. Output: '+out);
