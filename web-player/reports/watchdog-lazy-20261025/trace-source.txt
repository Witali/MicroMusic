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

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{'out-dir':{type:'string',default:'build/traces/current'},emsdk:{type:'string'},
  'physical-firmware':{type:'boolean',default:false},'eager-collector':{type:'boolean',default:false}}});
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
  'peripherals/system_gpio.c':['system_gpio_external','system_gpio_clock','system_gpio_advance','system_gpio_next_event_half'],
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
const functions=[];
for(const [file,names] of Object.entries(selected)){
  let text=readFileSync(join(native,file),'utf8');
  for(const name of names){
    const id=functions.length,pattern=new RegExp('(^[^(){};]*\\b'+name+'\\s*\\([^;{}]*\\)\\s*\\{)','gm');
    const matches=[...text.matchAll(pattern)];assert.equal(matches.length,1,file+': '+name+' definition');
    text=text.replace(pattern,'$1 MM_TRACE_HIT('+id+');');functions.push({id,name,source:'web-player/native/'+file});
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
void mm_trace_record(uint32_t id);
#define MM_TRACE_HIT(id) do { ++mm_trace_counts[id]; if(mm_trace_length<256)mm_trace_record(id); } while(0)
`);
const diagSource=join(out,'trace-counters.c');
writeFileSync(diagSource,`#include "trace-counters.h"
#include "native/peripherals/device.h"
uint64_t mm_trace_counts[${functions.length}];
uint32_t mm_trace_length;
typedef struct {uint64_t sequence,time,half;uint32_t id,reserved;} trace_entry_t;
static trace_entry_t entries[256];
void mm_trace_record(uint32_t id){
 entries[mm_trace_length]=(trace_entry_t){mm_trace_length,
  device_physical_mode()?device_time_ps():device_base_half(),device_virtual_half(),id,0};
 ++mm_trace_length;
}
void mm_trace_clear(void){for(unsigned n=0;n<${functions.length};n++)mm_trace_counts[n]=0;mm_trace_length=0;}
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
const args=[...manifest.flags.map(flag=>flag.replaceAll('<emsdk>',sdk)),'-include',diagHeader,
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
function make(entry,runtimeModule){
  const c=new ATtiny13A(entry.binary,entry.eeprom,{...entry.options,runtimeModule});
  if(entry.divisor){
    c.writeIO(IO.CLKPR,128);c.writeIO(IO.CLKPR,Math.log2(entry.divisor));
    const end=BigInt(entry.frames)*1000000000000n/48000n;
    assert.equal(c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:25000n,lowPs:25000n,
      transitionCount:end/25000n,knownUntilPs:end}),true);
  }
  return c;
}
function capture(c,entry){
  const blocks=[];
  for(let offset=0;offset<entry.frames;offset+=1024){
    const block=c.capturePhysical(Math.min(1024,entry.frames-offset),48000,entry.channels);
    blocks.push(Buffer.from(block.buffer,block.byteOffset,block.byteLength));
  }
  return Buffer.concat(blocks);
}
const stringify=v=>JSON.stringify(v,(_,v)=>typeof v==='bigint'?v.toString():v,2)+'\n';
const report={schema:'micromusic-native-call-trace-v1',createdAt:new Date().toISOString(),
  policy:{physicalFirmware:values['physical-firmware'],eagerCollector:values['eager-collector'],
    description:'Optional eager collector forces only the copied public PCM pressure query true; ordinary scheduling/CPU semantics stay unchanged. Counters never establish production elapsed time.'},
  git:{head:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim()},
  productionRuntimeSha256:sha(production),countedRuntimeSha256:sha(countedBytes),
  sourceSha256NormalizedLF:{...Object.fromEntries(Object.keys(manifest.inputs).map(p=>[p,sha(source(p))])),
    ...Object.fromEntries([...catalogPaths,'web-player/scripts/trace-device-calls.mjs',
      'web-player/lib/attiny13a-runtime.js','web-player/lib/avr-transpiler.js',
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
  assert.deepEqual(counted._state,original._state,entry.id+' full diagnostics');
  for(const name of ['data','rom','eeprom'])assert.deepEqual(counted[name],original[name],entry.id+' '+name);
  assert.deepEqual(counted.irqFrames,original.irqFrames);
  const physical=!!entry.options.resumable;
  const expectedPins=physical?original.drainPinsPs():original.drainPins(),
    actualPins=physical?counted.drainPinsPs():counted.drainPins();
  assert.deepEqual(actualPins,expectedPins,entry.id+' pin history');
  const row={id:entry.id,frames:entry.frames,sampleRate:48000,channels:entry.channels,
    requestedFirmwareId:entry.requestedFirmwareId,firmwareId:entry.firmwareId,flashSha256:sha(entry.binary),
    timeUnits:physical?'picoseconds':'oscillator half ticks',divisor:entry.divisor??1,
    cycles:counted.cyc,productionEquality:true,rawPcmSha256:sha(actual),pinSha256:sha(stringify(actualPins)),counts,prefix};
  report.results.push(row);console.log(entry.id,JSON.stringify(counts.filter(r=>[
    'clki_service','pin_voltages','analog_input','analog_adc_advance','next_event_scan','mirror'].includes(r.name))));
}
report.complete=true;writeFileSync(join(out,'summary.json'),stringify(report));
console.log('All source-entry counter/trace cases match production. Output: '+out);
