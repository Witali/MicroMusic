import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile,mkdtemp,writeFile,rm,stat} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {createPackage,decodePackage,assertPackageRuntimeABI,DEFAULT_CONFIGURATION,PACKAGE_LIMITS} from '../lib/attiny13a-package.js';
import {runtimeABI,transpileAVR} from '../lib/avr-transpiler.js';
import {normalizeClkiProfile,CLKI_PHASE_POLICY} from '../lib/devices/attiny13a-clki-profile.js';

const runtime=new Uint8Array(await readFile(new URL('../wasm/attiny13a.wasm',import.meta.url)));
const abi=runtimeABI(new WebAssembly.Instance(await WebAssembly.compile(runtime)).exports);
const flash=new Uint8Array([0x01,0xe0,0x08,0xbb,0xff,0xcf]); // LDI r16,1; OUT PORTB,r16; RJMP .
const generated=transpileAVR(flash,abi);
const input={flash,runtime,translated:generated.bytes,manifest:generated.manifest};
const original=await createPackage(input);
const copy=value=>JSON.parse(JSON.stringify(value));
const canonical=value=>value===null||typeof value!=='object'?JSON.stringify(value):Array.isArray(value)?'['+value.map(canonical).join(',')+']':'{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
function seal(pkg){const {integrity,...payload}=pkg;pkg.integrity={algorithm:'SHA-256',sha256:hash(canonical(payload))};return pkg;}
function replace(pkg,name,bytes){pkg.assets[name]={encoding:'base64',bytes:bytes.length,sha256:hash(bytes),data:Buffer.from(bytes).toString('base64')};return seal(pkg);}
const cli=fileURLToPath(new URL('../scripts/package-attiny13a.mjs',import.meta.url));

// Rewrite only section7 (name, external kind, index), retaining valid WASM.
// https://webassembly.github.io/spec/core/binary/modules.html#export-section
function rewriteExports(bytes,edit){
  let at=8;
  const readU32=()=>{let value=0,shift=0,b;do{b=bytes[at++];value+=(b&127)*2**shift;shift+=7;}while(b&128);return value;};
  const u32=value=>{const out=[];do{const b=value%128;value=Math.floor(value/128);out.push(b|(value?128:0));}while(value);return out;};
  const encoder=new TextEncoder(),decoder=new TextDecoder();
  while(at<bytes.length){
    const start=at,id=bytes[at++],size=readU32(),end=at+size;
    if(id!==7){at=end;continue;}
    const count=readU32(),entries=[];
    for(let i=0;i<count;i++){
      const length=readU32(),name=decoder.decode(bytes.subarray(at,at+length));at+=length;
      entries.push({name,kind:bytes[at++],index:readU32()});
    }
    assert.equal(at,end,'export section is fully decoded');
    const changed=edit(entries),body=[...u32(changed.length)];
    for(const entry of changed){
      const name=encoder.encode(entry.name);body.push(...u32(name.length),...name,entry.kind,...u32(entry.index));
    }
    return Uint8Array.from([...bytes.subarray(0,start),7,...u32(body.length),...body,...bytes.subarray(end)]);
  }
  assert.fail('runtime export section is missing');
}

function rewriteManifest(bytes,edit){
  let at=8;const encoder=new TextEncoder(),decoder=new TextDecoder();
  const read=()=>{let value=0,shift=0,b;do{b=bytes[at++];value+=(b&127)*2**shift;shift+=7;}while(b&128);return value;};
  const u32=v=>{const out=[];do{const b=v%128;v=Math.floor(v/128);out.push(b|(v?128:0));}while(v);return out;};
  while(at<bytes.length){
    const start=at,id=bytes[at++],size=read(),end=at+size;
    if(id!==0){at=end;continue;}
    const length=read(),name=decoder.decode(bytes.subarray(at,at+length));at+=length;
    if(name!=='micromusic.avr'){at=end;continue;}
    const manifest=JSON.parse(decoder.decode(bytes.subarray(at,end)));edit(manifest);
    const label=encoder.encode(name),json=encoder.encode(JSON.stringify(manifest));
    const body=Uint8Array.from([...u32(label.length),...label,...json]);
    return Uint8Array.from([...bytes.subarray(0,start),0,...u32(body.length),...body,...bytes.subarray(end)]);
  }
  assert.fail('translated manifest not found');
}

test('roundtrip contains complete Flash, EEPROM, runtime, translation, fuses and explicit timing options',async()=>{
  const eeprom=Uint8Array.from({length:64},(_,n)=>n);
  const pkg=await createPackage({...input,eeprom,configuration:{fuseLow:0x6a,fuseHigh:0xfe,lock:0xfc,oscillatorHz:4800000,wakeStartupHalf:1920,bodRecoveryNs:70000,factoryOsccal96:73,fuseStartupProfile:1}});
  const decoded=await decodePackage(JSON.stringify(pkg,null,2));
  assert.deepEqual(decoded.flash.subarray(0,flash.length),flash);assert.equal(decoded.flash.length,1024);
  assert.ok(decoded.flash.subarray(flash.length).every(x=>x===255));assert.deepEqual(decoded.eeprom,eeprom);
  assert.deepEqual(decoded.runtime,runtime);assert.deepEqual(decoded.translated,generated.bytes);
  assert.deepEqual(decoded.options,decoded.configuration);assert.equal(decoded.configuration.fuseLow,0x6a);
  assert.equal(decoded.configuration.fuseHigh,0xfe);assert.equal(decoded.configuration.lock,0xfc);
  assert.equal(decoded.configuration.bodRecoveryNs,70000);assert.equal(decoded.configuration.spmCommandCycles,0);
  assert.equal(decoded.configuration.factoryOsccal96,73);assert.equal(decoded.configuration.fuseStartupProfile,1);
  assertPackageRuntimeABI(decoded,abi);
});

test('default configuration, erased EEPROM and serialization are deterministic',async()=>{
  const decoded=await decodePackage(original);
  assert.deepEqual(decoded.configuration,DEFAULT_CONFIGURATION);
  assert.ok(decoded.eeprom.every(x=>x===255));assert.deepEqual(await createPackage(input),original);
  decoded.flash[0]=255;decoded.configuration.fuseLow=0;
  const again=await decodePackage(original);assert.equal(again.flash[0],flash[0]);assert.equal(again.configuration.fuseLow,0x7a);
});

test('version1 preserves its original configuration contract',async()=>{
  const pkg=copy(original);pkg.version=1;
  for(const key of ['osccalHz','nvmClockProfile','nvmCalibrationReferenceHz','powerResetProfile','resetInputProfile','resumable','clkiProfile'])delete pkg.configuration[key];
  const decoded=await decodePackage(seal(pkg));assert.equal(decoded.version,1);
  assert.deepEqual(decoded.configuration,pkg.configuration);assert.equal(Object.keys(decoded.options).length,17);
});

test('version2 preserves its calibrated-clock configuration contract',async()=>{
  const pkg=copy(original);pkg.version=2;delete pkg.configuration.powerResetProfile;delete pkg.configuration.resetInputProfile;
  delete pkg.configuration.resumable;delete pkg.configuration.clkiProfile;
  const decoded=await decodePackage(seal(pkg));assert.equal(decoded.version,2);assert.deepEqual(decoded.configuration,pkg.configuration);
});

test('version3 preserves its power-profile contract without requiring the later RESET profile',async()=>{
  const pkg=copy(original);pkg.version=3;delete pkg.configuration.resetInputProfile;
  delete pkg.configuration.resumable;delete pkg.configuration.clkiProfile;
  const decoded=await decodePackage(seal(pkg));assert.equal(decoded.version,3);
  assert.deepEqual(decoded.configuration,pkg.configuration);
});

test('version4 retains its RESET contract and rejects later continuation/CLKI fields',async()=>{
  const pkg=copy(original);pkg.version=4;delete pkg.configuration.resumable;delete pkg.configuration.clkiProfile;
  const decoded=await decodePackage(seal(pkg));assert.deepEqual(decoded.configuration,pkg.configuration);
  assert.equal(decoded.options.resumable,undefined);assert.equal(decoded.options.clkiProfile,undefined);
  for(const [key,value] of [['resumable',false],['clkiProfile',null]]){
    const bad=copy(pkg);bad.configuration[key]=value;
    await assert.rejects(decodePackage(seal(bad)),/unknown configuration/);
  }
});

test('packages reject DWEN without requiring an analog RESET profile',async()=>{
  for(const fuseHigh of [0xf7,0xf6,0xe7,0xe6])for(const lock of [0xff,0xfe,0xfd,0xfc]){
    const configuration={fuseHigh,lock};
    await assert.rejects(createPackage({...input,configuration}),/DWEN unprogrammed/);
    const pkg=copy(original);Object.assign(pkg.configuration,configuration);
    await assert.rejects(decodePackage(seal(pkg)),/DWEN unprogrammed/);
  }
});

test('the DWEN admission boundary also covers historical package versions',async()=>{
  const introduced={osccalHz:2,nvmClockProfile:2,nvmCalibrationReferenceHz:2,
    powerResetProfile:3,resetInputProfile:4,resumable:5,clkiProfile:5};
  for(let version=1;version<=5;version++){
    const pkg=copy(original);pkg.version=version;
    for(const [key,since] of Object.entries(introduced))if(version<since)delete pkg.configuration[key];
    // Establish that the complete historical schema itself is still accepted.
    await decodePackage(seal(pkg));pkg.configuration.fuseHigh=0xf7;
    await assert.rejects(decodePackage(seal(pkg)),/DWEN unprogrammed/);
  }
});

const phaseAbi=runtimeABI(new WebAssembly.Instance(await WebAssembly.compile(runtime)).exports,{resumable:true});
const phased=transpileAVR(flash,phaseAbi,{resumable:true});
const phaseConfiguration={resumable:true,osccalHz:Array.from({length:128},(_,n)=>n===0?9600000:0)};
const phaseInput={...input,translated:phased.bytes,manifest:phased.manifest,configuration:phaseConfiguration};

test('v5 binds the resumable execution mode, phase layout and configuration',async()=>{
  const pkg=await createPackage(phaseInput),decoded=await decodePackage(pkg);
  assert.equal(pkg.version,5);assert.equal(decoded.options.resumable,true);
  assert.equal(decoded.options.clkiProfile,null);assert.equal(decoded.manifest.executionMode,'resumable-v1');
  assert.deepEqual(decoded.abi.layout.phase,phaseAbi.phase);assertPackageRuntimeABI(decoded,phaseAbi);
  await assert.rejects(createPackage({...phaseInput,configuration:{}}),/execution mode mismatch/);
  await assert.rejects(createPackage({...input,configuration:phaseConfiguration}),/execution mode mismatch/);
  for(const patch of [{resumable:1},{resumable:null},{resumable:true,osccalHz:null}])
    await assert.rejects(createPackage({...phaseInput,configuration:{...phaseConfiguration,...patch}}),/configuration/);
});

test('v5 rejects malformed/overlapping phase metadata before any instantiation',async()=>{
  const cases=[
    [m=>m.abi.phase.bytes=81,/context layout/],
    [m=>m.abi.phase.stage=m.abi.phase.active,/overlapping phase/],
    [m=>m.abi.phase.retired--,/unaligned phase/],
    [m=>m.abi.phase.extra=0,/phase ABI fields/],
    [m=>{const p=m.abi.phase,delta=m.abi.data-p.pointer;for(const key of ['pointer','active','execPc','nextPc','stage','remaining','locals','temp','retired'])p[key]+=delta;},/overlapping ABI/],
    [m=>m.executionMode='resumable-v2',/execution mode/],
  ];
  for(const [edit,message] of cases){
    const translated=rewriteManifest(phased.bytes,edit);assert.equal(WebAssembly.validate(translated),true);
    await assert.rejects(createPackage({...phaseInput,manifest:undefined,translated}),message);
  }
});

test('v5 verifies every phase import and native phase observer signature',async()=>{
  for(const name of ['avr_device_phase_clock','avr_device_phase_deadline','avr_device_phase_retire',
    'avr_device_phase_enable','avr_device_phase_layout','avr_device_phase_active']){
    const missing=rewriteExports(runtime,entries=>entries.filter(e=>e.name!==name));
    await assert.rejects(createPackage({...phaseInput,runtime:missing}),/ABI function mismatch|runtime export mismatch/,name);
  }
  const bad=rewriteExports(runtime,entries=>{
    const target=entries.find(e=>e.name==='avr_device_phase_clock');
    target.index=entries.find(e=>e.name==='avr_device_phase_deadline').index;return entries;
  });
  await assert.rejects(createPackage({...phaseInput,runtime:bad}),/ABI function mismatch: phaseClock/);
});

test('CLKI profile is an exact digital fixture and requires CKSEL00 plus resumable mode',async()=>{
  const profile={phasePolicy:CLKI_PHASE_POLICY,initialLevel:0};
  assert.deepEqual(normalizeClkiProfile(profile),{...profile,electricalValidation:'none'});assert.notEqual(normalizeClkiProfile(profile),profile);
  for(const value of [{},{...profile,extra:0},{...profile,phasePolicy:'silicon'},
    {...profile,initialLevel:true},{...profile,initialLevel:2},{...profile,electricalValidation:true},
    {...profile,electricalValidation:'analog'},[],new Date()])
    assert.throws(()=>normalizeClkiProfile(value),/clkiProfile/);
  for(const patch of [{resumable:false},{fuseLow:0x7a},{clkiProfile:{...profile,initialLevel:-1}}])
    await assert.rejects(createPackage({...phaseInput,configuration:{resumable:true,fuseLow:0x78,clkiProfile:profile,...patch}}),/clkiProfile/);
  // This88-export runtime supports internal continuations, but has no CLKI
  // stream bridge yet. A profile must not silently fall back to nominal Hz.
  if(!new WebAssembly.Instance(new WebAssembly.Module(runtime)).exports.avr_device_configure_clki)
    await assert.rejects(createPackage({...phaseInput,configuration:{resumable:true,fuseLow:0x78,clkiProfile:profile}}),/runtime export mismatch: avr_device_configure_clki/);
});

test('v5 checks CLKI exports only for the selected source and verifies their exact signatures',async()=>{
  const configuration={resumable:true,fuseLow:0x78,clkiProfile:{phasePolicy:CLKI_PHASE_POLICY,initialLevel:1}};
  const clkiInput={...phaseInput,configuration},pkg=await createPackage(clkiInput);
  assert.deepEqual((await decodePackage(pkg)).configuration.clkiProfile,normalizeClkiProfile(configuration.clkiProfile));
  const missingPolicy=copy(pkg);delete missingPolicy.configuration.clkiProfile.electricalValidation;
  await assert.rejects(decodePackage(seal(missingPolicy)),/clkiProfile fields/);
  const names=['configure_clki','clki_enabled','clki_buffer','clki_capacity','clki_commit','clki_horizon_ps',
    'clki_count','clki_free','clki_level','clki_status','clki_aligned','clki_startup_ck'].map(n=>'avr_device_'+n);
  for(const name of names){
    const missing=rewriteExports(runtime,entries=>entries.filter(e=>e.name!==name));
    await assert.rejects(createPackage({...clkiInput,runtime:missing}),/runtime export mismatch/,name);
  }
  const absent=rewriteExports(runtime,entries=>entries.filter(e=>!names.includes(e.name)));
  await assert.doesNotReject(createPackage({...phaseInput,runtime:absent}),'Internal source never needs CLKI exports');
  const wrong=rewriteExports(runtime,entries=>{
    entries.find(e=>e.name==='avr_device_clki_status').index=entries.find(e=>e.name==='avr_device_clki_horizon_ps').index;
    return entries;
  });
  await assert.rejects(createPackage({...clkiInput,runtime:wrong}),/runtime export mismatch: avr_device_clki_status/);
});

test('CLI generates a matching v5 continuation when configuration requests resumable execution',async t=>{
  const dir=await mkdtemp(join(tmpdir(),'micromusic-phase-package-'));t.after(()=>rm(dir,{recursive:true,force:true}));
  const source=join(dir,'firmware.bin'),config=join(dir,'config.json'),output=join(dir,'package.json');
  await writeFile(source,flash);await writeFile(config,JSON.stringify(phaseConfiguration));
  const result=spawnSync(process.execPath,[cli,'pack',source,output,'--configuration',config],{encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);
  const decoded=await decodePackage(await readFile(output,'utf8'));
  assert.equal(decoded.version,5);assert.equal(decoded.manifest.executionMode,'resumable-v1');
  assert.equal(decoded.configuration.resumable,true);
});

test('package binds a calibrated clock table and programming profile',async()=>{
  const table=Array(128).fill(0);table[50]=9600000;table[51]=9696000;
  const configuration={factoryOsccal96:50,osccalHz:table,nvmClockProfile:1,nvmCalibrationReferenceHz:9600000};
  const pkg=await createPackage({...input,configuration}),decoded=await decodePackage(pkg);
  assert.equal(pkg.version,5);assert.deepEqual(decoded.configuration.osccalHz,table);
  decoded.options.osccalHz[50]=1;assert.equal(decoded.configuration.osccalHz[50],9600000);
  table[50]=1;assert.equal(pkg.configuration.osccalHz[50],9600000);
  const bad=copy(pkg);bad.configuration.osccalHz[51]++;
  await assert.rejects(decodePackage(bad),/SHA-256 mismatch/);
  for(const configuration of [{osccalHz:[]},{osccalHz:Array(128).fill(0)},
    {factoryOsccal96:51,osccalHz:pkg.configuration.osccalHz},
    {nvmClockProfile:1},{nvmClockProfile:2},{nvmCalibrationReferenceHz:1000000001}])
    await assert.rejects(createPackage({...input,configuration}),/configuration/);
  const external=await decodePackage(await createPackage({...input,configuration:{...configuration,fuseLow:0x78,oscillatorHz:1000000}}));
  assert.equal(external.configuration.oscillatorHz,1000000,'external source is independent of the internal RC calibration table');
});

test('power profiles are complete, copied and validated before constructing a runtime',async()=>{
  const osccalHz=Array(128).fill(0);osccalHz[0]=9600000;
  const powerResetProfile={porAssertMicrovolts:1300000,porReleaseMicrovolts:1400000,
    bod00Microvolts:4300000,bod01Microvolts:2700000,bod10Microvolts:1800000,
    bodHysteresisMicrovolts:50000,bodFilterNs:2000,bodRecoveryNs:60000,flashProgrammingMinMicrovolts:1800000};
  const configuration={osccalHz,powerResetProfile,vccMicrovolts:0};
  const pkg=await createPackage({...input,configuration}),decoded=await decodePackage(pkg);
  decoded.options.powerResetProfile.bodFilterNs=0;assert.equal(decoded.configuration.powerResetProfile.bodFilterNs,2000);
  powerResetProfile.bodFilterNs=1;assert.equal(pkg.configuration.powerResetProfile.bodFilterNs,2000);
  for(const bad of [{vccMicrovolts:0},
    {powerResetProfile:{...powerResetProfile},osccalHz:null},
    {...configuration,powerResetProfile:{...powerResetProfile,porReleaseMicrovolts:1}},
    {...configuration,powerResetProfile:{...powerResetProfile,bodHysteresisMicrovolts:10000000}},
    {...configuration,powerResetProfile:{...powerResetProfile,bodFilterNs:4294967296}},
    {...configuration,powerResetProfile:{...powerResetProfile,flashProgrammingMinMicrovolts:0}},
    {...configuration,powerResetProfile:{...powerResetProfile,unused:1}},
    {...configuration,powerResetProfile:{}}])await assert.rejects(createPackage({...input,configuration:bad}),/configuration/);
});

test('v4 RESET profiles reject invalid fields and unsupported clocks/fuses in writers and resealed packages',async()=>{
  const osccalHz=Array(128).fill(0);osccalHz[0]=9600000;
  const resetInputProfile={assertThresholdPpm:400000,releaseThresholdPpm:600000,
    assertQualificationNs:50,releaseQualificationNs:30,assertPropagationNs:20,releasePropagationNs:10};
  const configuration={osccalHz,resetInputProfile},pkg=await createPackage({...input,configuration});
  assert.equal(pkg.version,5);
  const cases=[
    ['missing fields',{resetInputProfile:{}},/resetInputProfile fields/],
    ['extra field',{resetInputProfile:{...resetInputProfile,unused:1}},/resetInputProfile fields/],
    ['assert threshold below range',{resetInputProfile:{...resetInputProfile,assertThresholdPpm:199999}},/assertThresholdPpm/],
    ['release threshold above range',{resetInputProfile:{...resetInputProfile,releaseThresholdPpm:900001}},/releaseThresholdPpm/],
    ['no hysteresis',{resetInputProfile:{...resetInputProfile,releaseThresholdPpm:400000}},/threshold hysteresis/],
    ['negative delay',{resetInputProfile:{...resetInputProfile,assertPropagationNs:-1}},/assertPropagationNs/],
    ['fractional delay',{resetInputProfile:{...resetInputProfile,releaseQualificationNs:1.5}},/releaseQualificationNs/],
    ['overflowing delay',{resetInputProfile:{...resetInputProfile,assertQualificationNs:0x100000000}},/assertQualificationNs/],
    ['no physical clock',{osccalHz:null},/physical time/],
    ['debugWIRE enabled',{fuseHigh:0xf7},/DWEN unprogrammed/],
  ];
  for(const [label,patch,message] of cases){
    await assert.rejects(createPackage({...input,configuration:{...configuration,...patch}}),message,label);
    const bad=copy(pkg);Object.assign(bad.configuration,patch);
    await assert.rejects(decodePackage(seal(bad)),message,label);
  }
  const omitted=copy(pkg);delete omitted.configuration.resetInputProfile;
  await assert.rejects(decodePackage(seal(omitted)),/configuration fields/);
});

test('decoding compiles and inspects WASM without constructing any instance',async()=>{
  const saved=WebAssembly.Instance;
  try{WebAssembly.Instance=class{constructor(){assert.fail('unverified module was instantiated');}};await decodePackage(original);}
  finally{WebAssembly.Instance=saved;}
});

test('format version, device and ABI identities are mandatory',async()=>{
  for(const mutate of [p=>p.version++,p=>p.format='other',p=>p.device='ATtiny85',p=>p.abi.id+='-other']){
    const pkg=copy(original);mutate(pkg);await assert.rejects(decodePackage(seal(pkg)),/unsupported/);
  }
});

test('integrity covers configuration and metadata as well as all binary components',async()=>{
  for(const mutate of [p=>p.configuration.fuseLow^=16,p=>p.manifest.optimizeFlags=false,p=>p.assets.eeprom.data='A'+p.assets.eeprom.data.slice(1)]){
    const pkg=copy(original);mutate(pkg);await assert.rejects(decodePackage(pkg),/package SHA-256 mismatch/);
  }
  for(const name of ['flash','eeprom','runtime','translated']){
    const pkg=copy(original);pkg.assets[name].sha256='0'.repeat(64);seal(pkg);
    await assert.rejects(decodePackage(pkg),/SHA-256 mismatch/);
  }
});

test('Flash is bound to all 512 decoded instruction words even with recalculated checksums',async()=>{
  const pkg=copy(original),bytes=Buffer.from(pkg.assets.flash.data,'base64');bytes[0]^=1;
  await assert.rejects(decodePackage(replace(pkg,'flash',bytes)),/Flash\/translation mapping mismatch/);
});

test('outer and embedded translation manifests and ABI layout must agree',async()=>{
  const pkg=copy(original);pkg.manifest.maxBlockInstructions=16;
  await assert.rejects(decodePackage(seal(pkg)),/manifest differs/);
  const other=copy(original);other.abi.layout.state.pc+=8;
  await assert.rejects(decodePackage(seal(other)),/ABI layout differs/);
  await assert.rejects(createPackage({...input,manifest:{...generated.manifest,optimizeFlags:false}}),/manifest differs/);
  const decoded=await decodePackage(original),bad=copy(abi);bad.state.pc+=8;
  assert.throws(()=>assertPackageRuntimeABI(decoded,bad),/ABI state must be contiguous/);
  const shifted=copy(abi);for(const field of Object.keys(shifted.state))shifted.state[field]+=8;
  assert.throws(()=>assertPackageRuntimeABI(decoded,shifted),/runtime ABI layout mismatch/);
});

test('invalid configuration, unknown options and omitted defaults are rejected',async()=>{
  for(const configuration of [{fuseLow:256},{fuseHigh:-1},{lock:1.5},{oscillatorHz:0},{watchdogHz:1000000001},
    {vccMicrovolts:2147483648},{adcFirstSample:28},{comparatorInitial:2},{flashMaximum:2},{wakeStartupHalf:4294967296},
    {factoryOsccal96:128},{fuseStartupProfile:true},{fuseStartupProfile:2},{fuseStartupProfile:1,fuseLow:0x7e},{fastIdle:true}]){
    await assert.rejects(createPackage({...input,configuration}),/configuration/);
  }
  const pkg=copy(original);delete pkg.configuration.watchdogHz;
  await assert.rejects(decodePackage(seal(pkg)),/configuration fields/);
});

test('Flash, EEPROM, WASM and JSON sizes are bounded before use',async()=>{
  for(const args of [{flash:new Uint8Array()},{flash:new Uint8Array(1025)},{eeprom:new Uint8Array(63)},
    {runtime:new Uint8Array(PACKAGE_LIMITS.runtime+1)},{translated:new Uint8Array(7)}]){
    await assert.rejects(createPackage({...input,...args}),/size/);
  }
  const pkg=copy(original);pkg.assets.flash.bytes=1025;
  await assert.rejects(decodePackage(seal(pkg)),/Flash size/);
  await assert.rejects(decodePackage(' '.repeat(PACKAGE_LIMITS.json+1)),/JSON size limit/);
  await assert.rejects(decodePackage('{'),/invalid JSON/);
});

test('base64 must be canonical and asset fields cannot be silently ignored',async()=>{
  const pkg=copy(original);pkg.assets.eeprom.data=pkg.assets.eeprom.data.slice(0,-1)+'!';
  await assert.rejects(decodePackage(seal(pkg)),/EEPROM base64/);
  const other=copy(original);other.assets.flash.url='https://example.invalid/flash.bin';
  await assert.rejects(decodePackage(seal(other)),/Flash fields/);
  const tail=copy(original);tail.assets.eeprom.data=tail.assets.eeprom.data.slice(0,-4)+'/x==';
  await assert.rejects(decodePackage(seal(tail)),/noncanonical EEPROM base64/);
});

test('runtime imports/start sections and truncated or mismatched WASM are rejected before execution',async()=>{
  const start=Uint8Array.from([0,97,115,109,1,0,0,0,8,1,0]);
  await assert.rejects(createPackage({...input,runtime:start}),/start section is forbidden/);
  // A tiny module importing an arbitrary host function (no instance is made).
  const hostImport=Uint8Array.from([0,97,115,109,1,0,0,0,1,4,1,0x60,0,0,2,7,1,1,120,1,121,0,0]);
  await assert.rejects(createPackage({...input,runtime:hostImport}),/runtime must not import/);
  await assert.rejects(createPackage({...input,runtime:runtime.subarray(0,30)}),/WASM|WebAssembly/);
  const legacy=new Uint8Array(await readFile(new URL('../wasm/avr.wasm',import.meta.url)));
  // The shared music runtime also has two pages, but no physical-board bus ABI.
  await assert.rejects(createPackage({...input,runtime:legacy}),/ABI function mismatch: readIO/);
  // Rename one same-length exported bridge without invalidating the WASM binary.
  const altered=runtime.slice(),needle=new TextEncoder().encode('avr_clock');let changed=false;
  for(let i=0;i<altered.length-needle.length;i++)if(needle.every((b,j)=>altered[i+j]===b)){altered[i]='x'.charCodeAt(0);changed=true;break;}
  assert.ok(changed);await assert.rejects(createPackage({...input,runtime:altered}),/ABI function mismatch: clock/);
});

test('v4 requires every RESET runtime export even when the profile is disabled',async()=>{
  assert.equal(original.configuration.resetInputProfile,null);
  for(const name of ['avr_device_configure_reset_input','avr_device_reset_input_enabled',
    'avr_device_reset_input_asserted','avr_device_reset_input_deadline_ps']){
    const altered=rewriteExports(runtime,entries=>{
      assert.ok(entries.some(entry=>entry.name===name&&entry.kind===0),name);
      return entries.map(entry=>entry.name===name?{...entry,name:'unavailable_'+name}:entry);
    });
    assert.equal(WebAssembly.validate(altered),true,'renaming preserves a valid module');
    const message=new RegExp('runtime export mismatch: '+name);
    await assert.rejects(createPackage({...input,runtime:altered}),message);
    await assert.rejects(decodePackage(replace(copy(original),'runtime',altered)),message);
  }
});

test('v4 rejects a RESET observer with an i64 result behind its expected i32 export name',async()=>{
  const name='avr_device_reset_input_enabled';
  const altered=rewriteExports(runtime,entries=>{
    const source=entries.find(entry=>entry.name==='avr_device_reset_input_deadline_ps'&&entry.kind===0);
    assert.ok(source,'existing native i64 observer supplies a valid function index');
    assert.ok(entries.some(entry=>entry.name===name&&entry.kind===0));
    return entries.map(entry=>entry.name===name?{...entry,index:source.index}:entry);
  });
  assert.equal(WebAssembly.validate(altered),true,'export alias changes no function bodies/types');
  const message=new RegExp('runtime export mismatch: '+name),saved=WebAssembly.Instance;
  try{
    WebAssembly.Instance=class{constructor(){assert.fail('incompatible runtime must not be instantiated');}};
    await assert.rejects(createPackage({...input,runtime:altered}),message);
    await assert.rejects(decodePackage(replace(copy(original),'runtime',altered)),message);
  }finally{WebAssembly.Instance=saved;}
});

test('CLI pack/verify/unpack preserves bytes and refuses tampered packages or existing outputs',async()=>{
  const directory=await mkdtemp(join(tmpdir(),'micromusic-attiny13a-package-'));
  const run=(...args)=>spawnSync(process.execPath,[cli,...args],{encoding:'utf8'});
  try{
    const source=join(directory,'firmware.bin'),out=join(directory,'device.json'),config=join(directory,'config.json');
    await writeFile(source,flash);await writeFile(config,JSON.stringify({fuseLow:0x6a,spmCommandCycles:4}));
    const packed=run('pack',source,out,'--configuration',config);assert.equal(packed.status,0,packed.stderr);
    const report=JSON.parse(packed.stdout);assert.equal(report.device,'ATtiny13A');assert.equal(report.configuration.fuseLow,0x6a);
    const verified=run('verify',out);assert.equal(verified.status,0,verified.stderr);assert.equal(JSON.parse(verified.stdout).integrity.sha256,report.integrity.sha256);
    const unpacked=join(directory,'unpacked'),extracted=run('unpack',out,unpacked);assert.equal(extracted.status,0,extracted.stderr);
    assert.deepEqual(new Uint8Array(await readFile(join(unpacked,'runtime.wasm'))),runtime);
    assert.deepEqual(new Uint8Array(await readFile(join(unpacked,'flash.bin'))).subarray(0,flash.length),flash);
    const repacked=join(directory,'repacked.json'),paired=run('pack',join(unpacked,'flash.bin'),repacked,
      '--translated',join(unpacked,'translated.wasm'),'--runtime',join(unpacked,'runtime.wasm'),
      '--eeprom',join(unpacked,'eeprom.bin'),'--configuration',join(unpacked,'configuration.json'));
    assert.equal(paired.status,0,paired.stderr);
    assert.equal(JSON.parse(paired.stdout).integrity.sha256,report.integrity.sha256);
    assert.equal(run('pack',source,out).status,1);assert.equal(run('unpack',out,unpacked).status,1);
    const pkg=JSON.parse(await readFile(out,'utf8'));pkg.configuration.fuseHigh^=1;await writeFile(out,JSON.stringify(pkg));
    const failed=run('verify',out);assert.equal(failed.status,1);assert.match(failed.stderr,/SHA-256 mismatch/);
    const badDir=join(directory,'must-not-exist');assert.equal(run('unpack',out,badDir).status,1);
    await assert.rejects(stat(badDir),{code:'ENOENT'});
  }finally{await rm(directory,{recursive:true,force:true});}
});
