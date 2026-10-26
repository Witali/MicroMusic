// Focused source/CPU/wire smoke control. None of these assertions is silicon evidence.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {existsSync,mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {dirname,join,relative,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {ATtiny13A} from '../lib/attiny13a-runtime.js';
import {AT13_IO as IO,AT13_MASK as MASK} from '../lib/attiny13a-registers.js';

const root=fileURLToPath(new URL('../../',import.meta.url)),args=process.argv.slice(2),options={};
while(args.length){
  const name=args.shift();
  if(!['--out','--avr-bin','--python'].includes(name)||!args.length)
    throw Error('Usage: verify-adc-sleep-probe.mjs [--out DIR] [--avr-bin DIR] [--python FILE]');
  options[name]=args.shift();
}
const folder=join(root,'web-player/native/peripherals'),configPath=join(folder,'adc-sleep-probe.json');
const config=JSON.parse(readFileSync(configPath,'utf8'));
assert.equal(config.schema,'micromusic-attiny13a-hardware-probe-v1');
assert.equal(config.status,'pending-hardware');assert.equal(config.expectedSiliconTrace,null);
assert.equal(config.probeId,5);assert.equal(config.expectedRecords,6);
assert.equal(config.profiles.length,4);assert.equal(config.wire.version,2);
const out=resolve(options['--out']??join(root,'build/adc-sleep-probe-verification'));
mkdirSync(out,{recursive:true});
const suffix=process.platform==='win32'?'.exe':'';
function locate(parts,file){
  for(let at=root;;at=dirname(at)){
    const candidate=join(at,...parts);
    if(existsSync(file?join(candidate,file):candidate))return candidate;
    if(at===dirname(at))return null;
  }
}
const avrBin=options['--avr-bin']&&resolve(options['--avr-bin'])||
  locate(['build','toolchains','avr-7.3.0','bin'],'avr-gcc'+suffix);
assert.ok(avrBin,'Supply --avr-bin pointing to the prepared portable AVR GCC/objcopy/size toolchain');
const python=options['--python']??process.env.PYTHON??
  locate(['build','toolchains','python-3.13.3',process.platform==='win32'?'python.exe':'python3'])??'python';
const run=(program,argv)=>{
  const result=spawnSync(program,argv,{cwd:root,encoding:'utf8'});
  if(result.error)throw result.error;
  assert.equal(result.status,0,result.stderr||result.stdout||program+' failed');
  return result.stdout.trim();
};
const avr=(name,argv)=>run(join(avrBin,name+suffix),argv);
const sha=bytes=>createHash('sha256').update(bytes).digest('hex'),hash=path=>sha(readFileSync(path));
const relativePath=path=>relative(root,path).replaceAll('\\','/');
const runtimePath=join(root,'web-player/wasm/attiny13a.wasm');
const runtimeModule=await WebAssembly.compile(readFileSync(runtimePath));
assert.deepEqual(WebAssembly.Module.imports(runtimeModule),[]);
const half=62500n,quantum=50000000n,limit=30000000000n;
function verify(profile,{hostInjected=false}={}){
  assert.ok(!hostInjected||profile.defines.PROBE_ADIE===0,'Positive control keeps ADIE=0');
  const directory=join(out,...(hostInjected?['host-injected-positive-controls']:[]),profile.id);
  mkdirSync(directory,{recursive:true});
  const elf=join(directory,'probe.elf'),image=join(directory,'probe.bin');
  avr('avr-gcc',['-mmcu=attiny13a','-nostdlib','-nostartfiles','-Wall','-Wextra','-Werror',
    '-Wl,--gc-sections','-Wl,-e,__vectors',
    ...Object.entries(profile.defines).map(([key,value])=>'-D'+key+'='+value),join(folder,config.firmware),'-o',elf]);
  avr('avr-objcopy',['-O','binary','-j','.text',elf,image]);
  writeFileSync(join(directory,'probe.lst'),avr('avr-objdump',['-d',elf])+'\n');
  const binary=readFileSync(image),size=avr('avr-size',[elf]).split(/\r?\n/).at(-1).trim().split(/\s+/).slice(0,3).map(Number);
  assert.deepEqual(size,[binary.length,0,0]);assert.ok(binary.length<=1024,'ATtiny13A Flash budget');
  const cpu=new ATtiny13A(binary,null,{runtimeModule,resumable:true,fastIdle:false,
    oscillatorHz:8000000,vccMicrovolts:5000000,watchdogHz:128000,
    fuseLow:0x70,fuseHigh:0xff,lock:0xff,fuseStartupProfile:1,adcFirstSample:27,
    clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}});
  // The complete source is delivered to the device. This smoke artifact retains
  // transport/marker transitions only, and is not a full mixed-signal capture.
  cpu.observePins(MASK.PINB0|MASK.PINB1|MASK.PINB4);
  assert.equal(cpu.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:half,lowPs:half,
    transitionCount:limit/half,knownUntilPs:limit}),true);
  cpu.setAnalogPs({at:0n,pin:2,microvolts:1000000});
  let csv='time_s,clock,data,marker\n',previous=cpu.state().pins.levels,bits=0;
  const markers=[];
  let hostInjection=null,completedWhileAsleep=null;
  const emit=(at,levels)=>{csv+=[Number(at)/1e12,Number(!!(levels&MASK.PINB1)),
    Number(!!(levels&MASK.PINB4)),Number(!!(levels&MASK.PINB0))].join(',')+'\n';};
  emit(0n,previous);
  const consume=()=>{
    for(const event of cpu.drainPinsPs()){
      const changed=previous^event.levels;
      if(changed&MASK.PINB0)markers.push({atPs:event.timePs.toString(),high:!!(event.levels&MASK.PINB0)});
      if((changed&MASK.PINB1)&&(event.levels&MASK.PINB1))++bits;
      previous=event.levels;emit(event.timePs,event.levels);
    }
  };
  consume();
  while(bits<config.expectedRecords*112){
    const now=cpu.state().timePs;
    assert.ok(now+quantum<limit,'Independent watchdog must permit a complete bounded acquisition');
    cpu.runUntilPs(now+quantum);consume();
    assert.equal(cpu.state().deviceFault,0,profile.id+' native fault');
    assert.equal(cpu.state().resetCount,0,'Watchdog interrupt must not reset the device');
    assert.ok(cpu.state().timePs>now);
    if(hostInjected&&!hostInjection&&cpu.state().sleeping){
      assert.deepEqual(markers.map(event=>event.high),[true],'Firmware entered its single measured SLEEP');
      assert.equal(cpu.state().irqs,0,'No interrupt before the host intervention');
      const before=cpu.readIO(IO.ADCSRA);
      assert.equal(before,MASK.ADEN|MASK.ADPS2|MASK.ADPS1,'No firmware-started conversion or ADIE');
      const atPs=cpu.state().timePs.toString(),written=before|MASK.ADSC;
      cpu.writeIO(IO.ADCSRA,written); // Debugger operation, never an AVR instruction.
      const after=cpu.readIO(IO.ADCSRA);
      assert.equal(after,written,'Only ADSC starts the synthetic positive control');
      assert.equal(cpu.state().timePs.toString(),atPs,'The host write must not advance time');
      hostInjection={kind:'synthetic-host-debugger-write',atPs,ioAddress:IO.ADCSRA,
        before,written,after,writeCount:1,firmwareSleepStartEvidence:false};
    }
    if(hostInjection&&!completedWhileAsleep&&
        cpu.state().timePs>=BigInt(hostInjection.atPs)+1000000000n){
      const adcsra=cpu.readIO(IO.ADCSRA),state=cpu.state();
      assert.equal(adcsra,MASK.ADEN|MASK.ADPS2|MASK.ADPS1|MASK.ADIF,'Injected conversion completed with ADIF retained, ADIE=0');
      assert.equal(state.sleeping,true,'ADIE=0 completion must not wake before the watchdog');
      assert.equal(state.irqs,0,'No ADC ISR acknowledges the positive-control flag');
      assert.deepEqual(markers.map(event=>event.high),[true],'No early first-wake witness');
      completedWhileAsleep={atPs:state.timePs.toString(),adcsra,sleeping:state.sleeping,irqs:state.irqs};
    }
  }
  cpu.runUntilPs(cpu.state().timePs+quantum);consume();
  assert.equal(bits,config.expectedRecords*112,'No duplicate/missing frames');
  assert.equal(cpu.state().pins.levels&MASK.PINB1,0,'Serializer finishes with clock low');
  const csvPath=join(directory,'transport.synthetic.csv'),decodedPath=join(directory,'decoded.synthetic.json');
  writeFileSync(csvPath,csv);
  // Pass a repository-relative waveform reference to avoid retaining machine
  // paths in the decoder output; no toolchain path is placed in the summary.
  run(python,[join(folder,'hardware-probe-decode.py'),relativePath(csvPath),
    '--config',configPath,'--profile',profile.id,'--capture-kind','synthetic','-o',decodedPath]);
  const trace=JSON.parse(readFileSync(decodedPath,'utf8')),records=trace.records;
  if(hostInjected){
    trace.syntheticControl={kind:'host-injected-positive-control',
      qualification:'Observability check only; not silicon behavior or firmware automatic sleep-start evidence',
      hostInjection,completedWhileAsleep};
    writeFileSync(decodedPath,JSON.stringify(trace,null,2)+'\n');
  }
  assert.equal(trace.status,'synthetic-decoder-test');assert.equal(trace.transportQuality,'complete-frames');
  assert.deepEqual(records.map(record=>record.sequence),[0,1,2,3,4,5]);
  assert.deepEqual(records.map(record=>record.data[5]),[0,1,2,3,4,5]);
  const enabled=profile.defines.PROBE_ADIE,base=MASK.ADEN|MASK.ADPS2|MASK.ADPS1|(enabled?MASK.ADIE:0);
  assert.deepEqual(records[0].data,[base,MASK.SE|(profile.defines.PROBE_SLEEP_MODE?MASK.SM0:0),MASK.WDTIE,1,MASK.ADC1D,0]);
  assert.equal(records[1].data[0],base,'ADSC=0 and ADIF=0 before the only sleep');
  assert.equal(records[1].data[1]|records[1].data[2]<<8,0,'No manual baseline conversion');
  assert.equal(records[1].data[3]&128,0);assert.equal(records[1].data[4],0);
  // These are deliberately the current model's predictions, not independently
  // established chip outcomes. Raw decoder bytes remain separately available.
  assert.equal(records[2].data[4],enabled,'ADC ISR count under current fixture');
  assert.equal(records[3].data[4],1,'Independent watchdog ISR always runs');
  assert.deepEqual(records[4].data,[enabled,enabled?2:1,enabled?2:1,0,0,4]);
  for(const record of [records[3],records[5]]){
    assert.equal(record.data[0],base|(hostInjected?MASK.ADIF:0),hostInjected?
      'Watchdog/final record preserves host-started conversion ADIF=1':
      'No pending ADIF under current ADIE-gated fixture');
    assert.equal(record.data[1]|record.data[2]<<8,(enabled||hostInjected)?204:0,'Raw firmware result at 1 V / 5 V');
    assert.equal(record.data[3]&128,0);
  }
  if(enabled){
    assert.equal(records[2].data[0],base,'ADC vector has already acknowledged ADIF');
    assert.equal(records[2].data[1]|records[2].data[2]<<8,204);
    assert.equal(records[2].data[3]&128,0);
  }else assert.deepEqual(records[2].data,[0,0,0,0,0,2],'Missing ISR has explicit zero evidence');
  assert.deepEqual(markers.map(event=>event.high),[true,false],'Exactly one sleep entry/first wake witness');
  const sleepSpan=BigInt(markers[1].atPs)-BigInt(markers[0].atPs);
  assert.ok(enabled?sleepSpan<1000000000n:sleepSpan>10000000000n,'ADC vs watchdog software wake control');
  assert.equal(cpu.state().irqs,enabled?2:1);
  if(hostInjected){assert.ok(hostInjection,'Exactly one host ADSC write is required');assert.ok(completedWhileAsleep);}
  const result={id:profile.id,defines:profile.defines,bytes:binary.length,imageSha256:hash(image),
    listingSha256:hash(join(directory,'probe.lst')),records:records.map(({sequence,data})=>({sequence,data})),markers,
    waveformSha256:hash(csvPath),decodedSha256:hash(decodedPath),translatedWasmSha256:sha(cpu.transpiledBytes),
    ...(hostInjected?{qualification:'Synthetic host-injected positive control; not silicon behavior or firmware sleep-start evidence',
      hostInjection,completedWhileAsleep}:{})};
  console.log(`${hostInjected?'host-injected-positive-controls/':''}${profile.id}: ${binary.length} bytes; source/CPU/wire software smoke passed`);
  return result;
}
const profiles=config.profiles.map(profile=>verify(profile));
const summary={schema:'micromusic-attiny13a-adc-sleep-probe-verification-v1',status:'software-verification-only',
  expectedSiliconTrace:null,qualification:'Current ADIE-gated fixture prediction; does not resolve the official documentation uncertainty',
  verificationScriptSha256:hash(fileURLToPath(import.meta.url)),sourceSha256:hash(join(folder,config.firmware)),
  descriptorSha256:hash(configPath),wireSha256:hash(join(folder,'probe-wire.inc')),
  registerDefinitionsSha256:hash(join(folder,'../attiny13a-registers.generated.inc')),
  decoderSha256:hash(join(folder,'hardware-probe-decode.py')),runtimeSha256:hash(runtimePath),
  toolchain:avr('avr-gcc',['--version']).split(/\r?\n/)[0],node:process.version,
  fixture:{clockHz:8000000,watchdogHz:128000,vccMicrovolts:5000000,adc1Microvolts:1000000,adcFirstSampleHalf:27,
    source:'continuous supplied periodic CLKI; digital-noninverting-zero-seed-v1',
    capture:'synthetic transport and marker only; no full clock/analog acquisition'},profiles};
writeFileSync(join(out,'summary.json'),JSON.stringify(summary,null,2)+'\n');
console.log('Four source-only ADC sleep controls passed; no hardware was programmed or measured.');
const positiveControls=config.profiles.filter(profile=>profile.defines.PROBE_ADIE===0)
  .map(profile=>verify(profile,{hostInjected:true}));
assert.equal(positiveControls.length,2);
for(const result of positiveControls){
  const original=profiles.find(profile=>profile.id===result.id);
  assert.equal(result.imageSha256,original.imageSha256,'Positive controls execute exactly the original firmware image');
  assert.equal(result.translatedWasmSha256,original.translatedWasmSha256);
}
writeFileSync(join(out,'host-injected-positive-controls','summary.json'),JSON.stringify({...summary,
  schema:'micromusic-attiny13a-adc-sleep-host-positive-verification-v1',
  status:'synthetic-host-injected-positive-control',
  qualification:'Host debugger writes ADSC once after firmware SLEEP; validates capture observability only, not silicon behavior or firmware automatic sleep start',
  profiles:positiveControls},null,2)+'\n');
console.log('Two separate host-injected ADIE=0 observability controls passed; no silicon outcome is asserted.');
