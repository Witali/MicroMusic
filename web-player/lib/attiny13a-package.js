// Portable package validation. No Node imports, host callbacks, or WASM instances.
// SHA-256 protects integrity; packages are executable code, not signed artifacts.
import {normalizeResetInputProfile} from './devices/attiny13a-reset-profile.js';
import {AT13_FUSE_MASK as FUSE} from './attiny13a-registers.js';
export const PACKAGE_FORMAT='micromusic-attiny13a-package';
export const PACKAGE_VERSION=4;
export const PACKAGE_ABI='micromusic-attiny13a-device-v1';
export const PACKAGE_LIMITS=Object.freeze({json:16*1024*1024,translated:4*1024*1024,runtime:2*1024*1024,manifest:512*1024});
export const DEFAULT_CONFIGURATION=Object.freeze({
  oscillatorHz:9600000,watchdogHz:128000,vccMicrovolts:5000000,bandgapMicrovolts:1100000,
  fuseLow:0x7a,fuseHigh:0xff,lock:0xff,adcFirstSample:27,
  comparatorPropagationHalf:0,bandgapStartupHalf:0,comparatorInitial:0,
  wakeStartupHalf:0,spmCommandCycles:0,flashMaximum:1,bodRecoveryNs:60000,
  factoryOsccal96:0,fuseStartupProfile:0,nvmClockProfile:0,nvmCalibrationReferenceHz:0,osccalHz:null,powerResetProfile:null,
  resetInputProfile:null,
});

const encoder=new TextEncoder(),decoder=new TextDecoder('utf-8',{fatal:true});
const fail=message=>{throw new Error('ATtiny13A package: '+message);};
const integer=(value,min,max,label)=>{
  if(!Number.isSafeInteger(value)||value<min||value>max)fail('invalid '+label);
  return value;
};
const record=(value,label)=>{
  if(!value||typeof value!=='object'||Array.isArray(value)||![Object.prototype,null].includes(Object.getPrototypeOf(value)))fail('invalid '+label);
};
function keys(value,expected,label){
  record(value,label);
  if(Object.keys(value).sort().join('\0')!==[...expected].sort().join('\0'))fail('unexpected '+label+' fields');
}
// Deterministic JSON over this format's finite numbers, strings, arrays and records.
// Bound depth/node count before hashing attacker-controlled metadata.
function canonical(value){
  let nodes=0;
  function visit(v,depth){
    if(++nodes>40000||depth>32)fail('metadata complexity limit');
    if(v===null||typeof v==='string'||typeof v==='boolean')return JSON.stringify(v);
    if(typeof v==='number'&&Number.isFinite(v))return JSON.stringify(v);
    if(Array.isArray(v))return '['+v.map(x=>visit(x,depth+1)).join(',')+']';
    record(v,'metadata');
    return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+visit(v[k],depth+1)).join(',')+'}';
  }
  return visit(value,0);
}
const equal=(a,b)=>canonical(a)===canonical(b);
async function sha256(bytes){
  if(!globalThis.crypto?.subtle)fail('WebCrypto SHA-256 is unavailable (use a secure browser context)');
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
}
function normalizeConfiguration(input={},complete=false,version=PACKAGE_VERSION){
  record(input,'configuration');
  const omitted=[...(version===1?['nvmClockProfile','nvmCalibrationReferenceHz','osccalHz','powerResetProfile']:version===2?['powerResetProfile']:[]),
    ...(version<4?['resetInputProfile']:[])];
  const defaults=Object.fromEntries(Object.entries(DEFAULT_CONFIGURATION).filter(([key])=>!omitted.includes(key)));
  for(const name of Object.keys(input))if(!Object.hasOwn(defaults,name))fail('unknown configuration '+name);
  if(complete)keys(input,Object.keys(defaults),'configuration');
  const configuration={...defaults,...input};
  for(const [name,value] of Object.entries(configuration)){
    if(name==='resetInputProfile'){
      try{configuration.resetInputProfile=normalizeResetInputProfile(value);}catch(error){fail(error.message);}
      if(value!==null&&(!configuration.osccalHz||!(configuration.fuseHigh&FUSE.HIGH_DWEN)))
        fail('configuration resetInputProfile requires physical time and DWEN unprogrammed');
      continue;
    }
    if(name==='powerResetProfile'){
      if(value!==null){
        const fields=['porAssertMicrovolts','porReleaseMicrovolts','bod00Microvolts','bod01Microvolts','bod10Microvolts',
          'bodHysteresisMicrovolts','bodFilterNs','bodRecoveryNs','flashProgrammingMinMicrovolts'];
        keys(value,fields,'configuration powerResetProfile');
        const p=Object.fromEntries(fields.map(key=>[key,integer(value[key],key==='bodHysteresisMicrovolts'||key.endsWith('Ns')?0:1,
          key.endsWith('Ns')?0xffffffff:0x7fffffff,'configuration powerResetProfile.'+key)]));
        if(!configuration.osccalHz||p.porReleaseMicrovolts<p.porAssertMicrovolts||
          ['bod00Microvolts','bod01Microvolts','bod10Microvolts'].some(key=>p[key]<=Math.floor(p.bodHysteresisMicrovolts/2)||p[key]+Math.ceil(p.bodHysteresisMicrovolts/2)>0x7fffffff))fail('invalid configuration powerResetProfile thresholds/clock');
        configuration.powerResetProfile=p;
      }
      continue;
    }
    if(name==='osccalHz'){
      if(value!==null){
        if(!Array.isArray(value)||value.length!==128||!value.some(Boolean))fail('invalid configuration osccalHz');
        configuration.osccalHz=Array.from(value,(hz,cal)=>integer(hz,0,1000000000,'configuration osccalHz['+cal+']'));
      }
      continue;
    }
    let min=0,max=0xffffffff;
    if(name==='oscillatorHz'||name==='watchdogHz'){min=1;max=1000000000;}
    if(name==='vccMicrovolts'||name==='bandgapMicrovolts'){min=name==='vccMicrovolts'&&configuration.powerResetProfile?0:1;max=0x7fffffff;}
    if(['fuseLow','fuseHigh','lock'].includes(name))max=255;
    if(name==='factoryOsccal96')max=127;
    if(['comparatorInitial','flashMaximum','fuseStartupProfile','nvmClockProfile'].includes(name))max=1;
    if(name==='nvmCalibrationReferenceHz')max=1000000000;
    integer(value,min,max,'configuration '+name);
    if(name==='adcFirstSample'&&![27,29].includes(value))fail('invalid configuration adcFirstSample');
  }
  if(configuration.nvmClockProfile===1&&!configuration.nvmCalibrationReferenceHz)fail('configuration nvmClockProfile requires a calibration reference');
  if(configuration.fuseStartupProfile&&((configuration.fuseLow>>2)&3)===3)fail('configuration fuseStartupProfile uses reserved SUT11');
  if(configuration.osccalHz){
    const factory=configuration.osccalHz[configuration.factoryOsccal96];
    if(!factory||([1,2].includes(configuration.fuseLow&3)&&factory!==configuration.oscillatorHz))fail('configuration OSCCAL factory frequency/clock source mismatch');
  }
  return configuration;
}
function image(input,length,label,optional=false){
  if(optional&&input==null)return new Uint8Array(length).fill(255);
  if(!(input instanceof Uint8Array)||!input.length||input.length>length||(label==='EEPROM'&&input.length!==length))fail('invalid '+label+' size');
  const output=new Uint8Array(length).fill(255);output.set(input);return output;
}
function code(input,limit,label){
  if(!(input instanceof Uint8Array)||input.length<8||input.length>limit)fail('invalid '+label+' size');
  return input.slice();
}
function base64(bytes){
  let text='';
  for(let i=0;i<bytes.length;i+=16384)text+=String.fromCharCode(...bytes.subarray(i,i+16384));
  return btoa(text);
}
async function asset(bytes){return {encoding:'base64',bytes:bytes.length,sha256:await sha256(bytes),data:base64(bytes)};}
async function readAsset(value,min,max,label){
  keys(value,['encoding','bytes','sha256','data'],label);
  integer(value.bytes,min,max,label+' size');
  if(value.encoding!=='base64'||typeof value.data!=='string'||value.data.length!==4*Math.ceil(value.bytes/3)||
    /[^A-Za-z0-9+/=]/.test(value.data))fail('invalid '+label+' base64');
  if(typeof value.sha256!=='string'||!/[0-9a-f]{64}/.test(value.sha256)||value.sha256.length!==64)fail('invalid '+label+' SHA-256');
  let raw;try{raw=atob(value.data);}catch{fail('invalid '+label+' base64');}
  const bytes=Uint8Array.from(raw,c=>c.charCodeAt(0));
  if(bytes.length!==value.bytes||base64(bytes)!==value.data)fail('noncanonical '+label+' base64');
  if(await sha256(bytes)!==value.sha256)fail(label+' SHA-256 mismatch');
  return bytes;
}

// Inspect only the MVP ABI sections; the engine validates the entire binary.
// Reject start sections so even a future loader cannot execute initialization code.
// Binary grammar: https://webassembly.github.io/spec/core/binary/modules.html
function inspectWasm(bytes,label){
  let at=0,end=bytes.length;
  const byte=()=>{if(at>=end)fail('truncated '+label+' WASM');return bytes[at++];};
  function u32(){
    let value=0;
    for(let shift=0;shift<=28;shift+=7){const b=byte();if(shift===28&&(b&0xf0))fail('invalid WASM u32');value+=(b&127)*2**shift;if(!(b&128))return value;}
    fail('invalid WASM u32');
  }
  function name(){const length=u32();if(length>end-at)fail('truncated WASM name');const value=decoder.decode(bytes.subarray(at,at+length));at+=length;return value;}
  function vector(read){const count=u32();if(count>end-at)fail('invalid WASM vector');return Array.from({length:count},read);}
  function limits(){const flags=byte();if(flags!==1)fail(label+' must use fixed, unshared wasm32 memory');const min=u32(),max=u32();return {min,max};}
  const signature=()=>{if(byte()!==0x60)fail('unsupported WASM function type');return {params:vector(byte),results:vector(byte)};};
  const types=[],functions=[],imports=[],exports=[],memories=[],tables=[];
  if([0,97,115,109,1,0,0,0].some(b=>byte()!==b))fail('invalid '+label+' WASM header');
  while(at<bytes.length){
    end=bytes.length;const id=byte(),length=u32(),next=at+length;
    if(next>bytes.length)fail('truncated '+label+' WASM section');end=next;
    if(id===8)fail(label+' WASM start section is forbidden');
    if(id===1)types.push(...vector(signature));
    else if(id===2)imports.push(...vector(()=>{
      const module=name(),field=name(),kind=byte();
      if(kind===0){const type=u32();functions.push(type);return {module,name:field,kind,type};}
      if(kind===2){const memory=limits();memories.push(memory);return {module,name:field,kind,memory};}
      fail(label+' has unsupported WASM imports');
    }));
    else if(id===3)functions.push(...vector(u32));
    else if(id===4)tables.push(...vector(()=>{
      if(byte()!==0x70)fail('unsupported WASM table type');
      const table=limits();if(table.min>16384||table.max>16384)fail('WASM table size limit');return table;
    }));
    else if(id===5)memories.push(...vector(limits));
    else if(id===7)exports.push(...vector(()=>({name:name(),kind:byte(),index:u32()})));
    else at=next;
    if(at!==next)fail('invalid '+label+' WASM section length');
  }
  return {imports,exports,memories,tables,signature:index=>types[functions[index]]};
}

const bridges={clock:'avr_clock',interrupt:'avr_interrupt',writeIO:'avr_write_io',idle:'avr_idle',
  readIO:'avr_read_io',writeMasked:'avr_write_io_masked',ready:'avr_device_ready',time:'avr_device_time',
  wait:'avr_device_wait',control:'avr_device_control',lpm:'avr_device_lpm',audioDeadline:'avr_device_audio_deadline',
  audioSample:'avr_device_audio_sample',pending:'avr_device_pending',cpuDeadline:'avr_device_cpu_deadline',idleUntil:'avr_device_idle'};
const i32=0x7f,i64=0x7e,f64=0x7c,signature=(params=[],results=[])=>({params,results});
const bridgeSignatures={clock:signature([f64]),interrupt:signature(),writeIO:signature([i32,i32],[i32]),idle:signature([],[i32]),
  readIO:signature([i32],[i32]),writeMasked:signature([i32,i32,i32],[i32]),ready:signature([],[i32]),time:signature([],[f64]),
  wait:signature([f64],[i32]),control:signature([i32,i32,i32],[i32]),lpm:signature([i32],[i32]),audioDeadline:signature([],[f64]),
  audioSample:signature([i32],[i32]),pending:signature([],[i32]),cpuDeadline:signature([f64],[f64]),idleUntil:signature([f64],[i32])};
function validateABI(abi){
  keys(abi,['state','data','rom','idle','frames','pwm','memoryPages','device'],'ABI layout');
  if(abi.device!==true)fail('ABI requires the full-device runtime');
  integer(abi.memoryPages,1,256,'ABI memoryPages');record(abi.state,'ABI state');
  const limit=abi.memoryPages*65536,offsets=Object.values(abi.state);
  if(offsets.length<8||offsets.length>128)fail('invalid ABI state count');
  for(const required of ['pc','cyc','error','errorPC','irqDelay','overflowAt','writes','frameCount'])if(!Object.hasOwn(abi.state,required))fail('ABI state missing '+required);
  for(const [name,offset] of Object.entries(abi.state)){
    if(!/^[A-Za-z][A-Za-z0-9]*$/.test(name))fail('invalid ABI state name');
    integer(offset,0,limit-8,'ABI state offset');if(offset%8)fail('unaligned ABI state');
  }
  const sorted=[...offsets].sort((a,b)=>a-b);
  if(sorted.some((offset,i)=>offset!==sorted[0]+8*i))fail('ABI state must be contiguous');
  const regions=[[sorted[0],offsets.length*8]];
  for(const [name,size,alignment] of [['data',160,1],['rom',1024,1],['idle',512,1],['frames',256,8],['pwm',16384,4]]){
    integer(abi[name],0,limit-size,'ABI '+name);if(abi[name]%alignment)fail('unaligned ABI '+name);
    regions.push([abi[name],size]);
  }
  regions.sort((a,b)=>a[0]-b[0]);
  if(regions.some((r,i)=>i&&r[0]<regions[i-1][0]+regions[i-1][1]))fail('overlapping ABI regions');
}
function validateManifest(manifest,flash){
  record(manifest,'manifest');
  if(encoder.encode(canonical(manifest)).length>PACKAGE_LIMITS.manifest)fail('manifest size limit');
  if(manifest.schema!=='micromusic-avr-transpiled-v1'||manifest.device!=='ATtiny13A')fail('unsupported translated manifest/device');
  validateABI(manifest.abi);
  if(typeof manifest.optimizeFlags!=='boolean')fail('invalid flag optimization setting');
  integer(manifest.maxBlockInstructions,2,64,'block size');
  if(!Array.isArray(manifest.mapping)||manifest.mapping.length!==512)fail('invalid Flash mapping');
  for(let pc=0;pc<512;pc++){
    const item=manifest.mapping[pc];
    if(item?.pc!==pc||item.byteAddress!==pc*2||item.word!==(flash[pc*2]|flash[pc*2+1]<<8))fail('Flash/translation mapping mismatch at word '+pc);
  }
}
async function validateCode(translated,runtime,flash,manifest,version=PACKAGE_VERSION){
  const t=inspectWasm(translated,'translated'),r=inspectWasm(runtime,'runtime');
  const [translatedModule]=await Promise.all([WebAssembly.compile(translated),WebAssembly.compile(runtime)]);
  const sections=WebAssembly.Module.customSections(translatedModule,'micromusic.avr');
  if(sections.length!==1||sections[0].byteLength>PACKAGE_LIMITS.manifest)fail('missing/oversized translated manifest section');
  let embedded;try{embedded=JSON.parse(decoder.decode(sections[0]));}catch{fail('invalid embedded translated manifest');}
  validateManifest(embedded,flash);
  if(manifest!==undefined&&!equal(manifest,embedded))fail('manifest differs from translated WASM');
  const pages=embedded.abi.memoryPages;
  if(r.imports.length)fail('runtime must not import host functions or memory');
  if(t.tables.length!==1||t.tables[0].min!==1024||t.tables[0].max!==1024)fail('translated dispatch table mismatch');
  if(r.memories.length!==1||t.memories.length!==1||[...r.memories,...t.memories].some(m=>m.min!==pages||m.max!==pages))fail('ABI memory size mismatch');
  if(!r.exports.some(e=>e.name==='memory'&&e.kind===2&&e.index===0))fail('runtime memory export is missing');
  const names=new Set();
  for(const item of t.imports){
    if(item.module!=='avr'||names.has(item.name))fail('invalid translated imports');names.add(item.name);
    if(item.kind===2&&item.name==='memory')continue;
    const target=bridges[item.name],exported=r.exports.find(e=>e.name===target&&e.kind===0);
    if(item.kind!==0||!target||!exported||!equal(t.signature(t.imports.filter(i=>i.kind===0).indexOf(item)),bridgeSignatures[item.name])||!equal(bridgeSignatures[item.name],r.signature(exported.index)))fail('ABI function mismatch: '+item.name);
  }
  if(!equal([...names].sort(),['memory',...Object.keys(bridges)].sort()))fail('incomplete full-device translated imports');
  for(const [name,type] of Object.entries({avr_layout:signature([i32],[i32]),avr_field_name:signature([i32],[i32]),
    avr_device_configure:signature([i32,i32],[i32]),avr_reset:signature([i32,i32])})){
    const exported=r.exports.find(e=>e.name===name&&e.kind===0);
    if(!exported||!equal(r.signature(exported.index),type))fail('runtime export mismatch: '+name);
  }
  if(version>=2)for(const [name,type] of Object.entries({
    avr_device_configure_osccal_hz:signature([i32,i32],[i32]),avr_device_physical_mode:signature([],[i32]),
    avr_device_rebase_time:signature([],[i64]),avr_device_time_ps:signature([],[i64]),avr_device_startup_deadline_ps:signature([],[i64]),
    avr_device_oscillator_hz:signature([],[i32]),avr_device_inject_pins_ps:signature([i64,i32,i32],[i32]),
    avr_device_inject_analog_ps:signature([i64,i32,i32],[i32]),avr_device_pin_buffer_ps:signature([],[i32]),
    avr_device_pin_count_ps:signature([],[i32]),avr_device_pins_ps:signature([],[i32]),
  })){
    const exported=r.exports.find(e=>e.name===name&&e.kind===0);
    if(!exported||!equal(r.signature(exported.index),type))fail('runtime export mismatch: '+name);
  }
  if(version>=3)for(const [name,type] of Object.entries({avr_device_configure_power:signature([i32,i32],[i32]),
    avr_device_inject_vcc_ps:signature([i64,i32],[i32]),avr_device_power_enabled:signature([],[i32]),avr_device_vcc_microvolts:signature([],[i32])})){
    const exported=r.exports.find(e=>e.name===name&&e.kind===0);
    if(!exported||!equal(r.signature(exported.index),type))fail('runtime export mismatch: '+name);
  }
  if(version>=4)for(const [name,type] of Object.entries({avr_device_configure_reset_input:signature([i32,i32],[i32]),
    avr_device_reset_input_enabled:signature([],[i32]),avr_device_reset_input_asserted:signature([],[i32]),
    avr_device_reset_input_deadline_ps:signature([],[i64])})){
    const exported=r.exports.find(e=>e.name===name&&e.kind===0);
    if(!exported||!equal(r.signature(exported.index),type))fail('runtime export mismatch: '+name);
  }
  for(const [name,type] of Object.entries({step:signature(),block:signature([f64,i32],[i32]),run:signature([i32],[i32]),
    nextDuty:signature([],[i32]),capturePWM:signature([i32,i32],[i32]),runUntil:signature([f64],[i32]),capturePhysical:signature([i32],[i32])})){
    const exported=t.exports.find(e=>e.name===name&&e.kind===0);
    if(!exported||!equal(t.signature(exported.index),type))fail('translated export mismatch: '+name);
  }
  for(const name of ['controlRequest','watchdogResetCycle','debugEnabled','captureFault'])if(!t.exports.some(e=>e.name===name&&e.kind===3))fail('translated global missing '+name);
  return embedded;
}

/** Return a self-contained JSON-serializable object; Flash is padded with 0xff. */
export async function createPackage({flash,eeprom,configuration={},translated,runtime,manifest}){
  flash=image(flash,1024,'Flash');eeprom=image(eeprom,64,'EEPROM',true);
  translated=code(translated,PACKAGE_LIMITS.translated,'translated');runtime=code(runtime,PACKAGE_LIMITS.runtime,'runtime');
  configuration=normalizeConfiguration(configuration);
  manifest=await validateCode(translated,runtime,flash,manifest);
  const assets=Object.fromEntries(await Promise.all(Object.entries({flash,eeprom,translated,runtime}).map(async([name,bytes])=>[name,await asset(bytes)])));
  const pkg={format:PACKAGE_FORMAT,version:PACKAGE_VERSION,device:'ATtiny13A',
    abi:{id:PACKAGE_ABI,layout:manifest.abi},configuration,manifest,assets};
  pkg.integrity={algorithm:'SHA-256',sha256:await sha256(encoder.encode(canonical(pkg)))};
  return pkg;
}

/** Verify before any WASM instantiation. Returned bytes/options are fresh copies. */
export async function decodePackage(json){
  if(typeof json!=='string')json=canonical(json);
  if(json.length>PACKAGE_LIMITS.json||encoder.encode(json).length>PACKAGE_LIMITS.json)fail('JSON size limit');
  let pkg;try{pkg=JSON.parse(json);}catch{fail('invalid JSON');}
  keys(pkg,['format','version','device','abi','configuration','manifest','assets','integrity'],'package');
  if(pkg.format!==PACKAGE_FORMAT||![1,2,3,PACKAGE_VERSION].includes(pkg.version))fail('unsupported format/version');
  if(pkg.device!=='ATtiny13A')fail('unsupported device');
  keys(pkg.abi,['id','layout'],'ABI');if(pkg.abi.id!==PACKAGE_ABI)fail('unsupported ABI identity');
  const configuration=normalizeConfiguration(pkg.configuration,true,pkg.version);
  keys(pkg.assets,['flash','eeprom','translated','runtime'],'assets');
  keys(pkg.integrity,['algorithm','sha256'],'integrity');
  const {integrity,...payload}=pkg;
  if(integrity.algorithm!=='SHA-256'||integrity.sha256!==await sha256(encoder.encode(canonical(payload))))fail('package SHA-256 mismatch');
  const [flash,eeprom,translated,runtime]=await Promise.all([
    readAsset(pkg.assets.flash,1024,1024,'Flash'),readAsset(pkg.assets.eeprom,64,64,'EEPROM'),
    readAsset(pkg.assets.translated,8,PACKAGE_LIMITS.translated,'translated'),readAsset(pkg.assets.runtime,8,PACKAGE_LIMITS.runtime,'runtime'),
  ]);
  const manifest=await validateCode(translated,runtime,flash,pkg.manifest,pkg.version);
  if(!equal(pkg.abi.layout,manifest.abi))fail('ABI layout differs from translation');
  return {version:pkg.version,flash,eeprom,translated,runtime,configuration,options:structuredClone(configuration),manifest,abi:pkg.abi,integrity:{...integrity}};
}

/** Compare the verified descriptor with runtimeABI(instance.exports) before linking. */
export function assertPackageRuntimeABI(decoded,actualABI){
  validateABI(actualABI);
  if(!equal(decoded.abi?.layout,actualABI))fail('instantiated runtime ABI layout mismatch');
}
