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
  for(const key of ['osccalHz','nvmClockProfile','nvmCalibrationReferenceHz','powerResetProfile'])delete pkg.configuration[key];
  const decoded=await decodePackage(seal(pkg));assert.equal(decoded.version,1);
  assert.deepEqual(decoded.configuration,pkg.configuration);assert.equal(Object.keys(decoded.options).length,17);
});

test('version2 preserves its calibrated-clock configuration contract',async()=>{
  const pkg=copy(original);pkg.version=2;delete pkg.configuration.powerResetProfile;
  const decoded=await decodePackage(seal(pkg));assert.equal(decoded.version,2);assert.deepEqual(decoded.configuration,pkg.configuration);
});

test('package binds a calibrated clock table and programming profile',async()=>{
  const table=Array(128).fill(0);table[50]=9600000;table[51]=9696000;
  const configuration={factoryOsccal96:50,osccalHz:table,nvmClockProfile:1,nvmCalibrationReferenceHz:9600000};
  const pkg=await createPackage({...input,configuration}),decoded=await decodePackage(pkg);
  assert.equal(pkg.version,3);assert.deepEqual(decoded.configuration.osccalHz,table);
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
  await assert.rejects(createPackage({...input,runtime:legacy}),/ABI memory size mismatch/);
  // Rename one same-length exported bridge without invalidating the WASM binary.
  const altered=runtime.slice(),needle=new TextEncoder().encode('avr_clock');let changed=false;
  for(let i=0;i<altered.length-needle.length;i++)if(needle.every((b,j)=>altered[i+j]===b)){altered[i]='x'.charCodeAt(0);changed=true;break;}
  assert.ok(changed);await assert.rejects(createPackage({...input,runtime:altered}),/ABI function mismatch: clock/);
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
