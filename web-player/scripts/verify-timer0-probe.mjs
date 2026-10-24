// Build source-only probes; execute documented nonzero controls, never TOP=0.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {existsSync,mkdirSync,readdirSync,readFileSync,writeFileSync} from 'node:fs';
import {dirname,join,relative,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {AT13_IO as IO,AT13_BIT as BIT} from '../lib/attiny13a-registers.js';
import {ATtiny13A} from '../lib/attiny13a.js';

const root=fileURLToPath(new URL('../../',import.meta.url));
const args=process.argv.slice(2),options={};
while(args.length){
  const name=args.shift();
  if(!['--avr-bin','--out','--source','--python'].includes(name)||!args.length)throw Error('Usage: node web-player/scripts/verify-timer0-probe.mjs [--avr-bin DIR] [--python FILE] [--out DIR] [--source FILE]');
  options[name]=args.shift();
}
let avrBin=options['--avr-bin']&&resolve(options['--avr-bin']);
const suffix=process.platform==='win32'?'.exe':'';
if(!avrBin)for(let folder=root;;folder=dirname(folder)){
  const candidate=join(folder,'build/toolchains/avr-7.3.0/bin');
  if(existsSync(join(candidate,'avr-gcc'+suffix))){avrBin=candidate;break;}
  if(folder===dirname(folder))break;
}
if(!avrBin)throw Error('Supply --avr-bin pointing to AVR GCC/objcopy/size.');
const out=resolve(options['--out']??join(root,'build/timer0-probe-verification'));
mkdirSync(out,{recursive:true});
const folder=join(root,'web-player/native/peripherals');
const configPath=join(folder,'timer0-top-zero-probe.json');
const config=JSON.parse(readFileSync(configPath,'utf8'));
const source=resolve(options['--source']??join(folder,config.firmware));
const vendor=join(root,'web-player/vendor/microchip/ATtiny_DFP/3.4.278');
const atdfPath=join(vendor,'atdf/ATtiny13A.atdf');
const atdf=readFileSync(atdfPath,'utf8');
const tc0=atdf.match(/<instance\s+name="TC0"[^>]*>([\s\S]*?)<\/instance>/)?.[1];
assert.ok(tc0,'Manufacturer TC0 signal definitions');
const signals=Object.fromEntries([...tc0.matchAll(/<signal\s+group="([^"]+)"\s+pad="([^"]+)"/g)].map(m=>[m[1],m[2]]));
assert.equal(config.pins.t0,signals.T,'T0 pin must match the pinned manufacturer ATDF');
assert.equal(config.pins.oc0a,signals.OCA);assert.equal(config.pins.oc0b,signals.OCB);
assert.equal(config.clock.timerSource,'external-T0-rising-'+signals.T);
assert.equal(new Set(Object.values(config.pins).map(pin=>pin.split('/')[0])).size,6,'Probe pin roles must not overlap');
const mask=role=>1<<BIT['PINB'+config.pins[role].match(/^PB([0-5])$/)[1]];
const t0Mask=mask('t0'),clockMask=mask('clock'),dataMask=mask('data');
const hashBytes=bytes=>createHash('sha256').update(bytes).digest('hex');
const hash=path=>hashBytes(readFileSync(path));
// Hash the whole small lib source tree, a conservative superset of the static
// and dynamic imports used by construction, translation and public execution.
const librarySources={};
const scanSources=folder=>{
  for(const entry of readdirSync(folder,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))){
    const path=join(folder,entry.name);
    if(entry.isDirectory())scanSources(path);
    else if(entry.isFile()&&entry.name.endsWith('.js'))librarySources[relative(root,path).replaceAll('\\','/')]=hash(path);
  }
};
scanSources(join(root,'web-player/lib'));
const run=(program,parameters)=>{
  const result=spawnSync(program,parameters,{cwd:root,encoding:'utf8'});
  if(result.error)throw result.error;
  assert.equal(result.status,0,result.stderr||result.stdout||program+' failed');
  return result.stdout.trim();
};
const avr=(tool,parameters)=>run(join(avrBin,tool+suffix),parameters);
const controls=new Map([
  ['control-fixed-top-255',[1,2,3,4]],
  ['control-variable-top-3',[1,2,3,2]],
  ['control-variable-top-1-b-zero',[1,0,1,0]],
  ['control-variable-top-1-b-one',[1,0,1,0]],
]);
const profiles=[];
for(const profile of config.profiles){
  assert.match(profile.id,/^[a-z0-9-]+$/);
  const elf=join(out,profile.id+'.elf'),image=join(out,profile.id+'.bin');
  avr('avr-gcc',['-mmcu=attiny13a','-nostdlib','-nostartfiles','-Wl,--gc-sections','-Wl,-e,__vectors',
    ...Object.entries(profile.defines).map(([key,value])=>'-D'+key+'='+value),
    '-I'+folder,source,'-o',elf]);
  avr('avr-objcopy',['-O','binary','-j','.text',elf,image]);
  const size=avr('avr-size',[elf]).split(/\r?\n/).at(-1).trim().split(/\s+/).slice(0,3).map(Number);
  const binary=readFileSync(image);
  assert.equal(binary.length,size[0],profile.id+' .text size');
  assert.ok(binary.length<=1024,profile.id+' Flash capacity');
  assert.deepEqual(size.slice(1),[0,0],profile.id+' no data/BSS initialization');
  const record={id:profile.id,bytes:binary.length,sha256:hash(image),defines:profile.defines,softwareControl:null};
  if(controls.has(profile.id)){
    assert.notEqual(profile.defines.PROBE_INITIAL_TOP,0,'Do not emulate the ambiguous measurement profiles');
    const cpu=new ATtiny13A(binary,undefined,{oscillatorHz:config.clock.nominalOscillatorHz,
      fuseLow:Number(config.fuses.low),fuseHigh:Number(config.fuses.high),lock:Number(config.fuses.lock),
      fuseStartupProfile:0,fastIdle:false});
    cpu.injectPins({at:0n,mask:t0Mask,levels:0});
    const events=[];
    const advanceTo=end=>{
      for(let now=cpu.state().baseHalf;now<end;now=cpu.state().baseHalf){
        cpu.runUntil(now+256n<end?now+256n:end);
        events.push(...cpu.drainPins());
        assert.equal(cpu.state().deviceFault,0,profile.id+' peripheral fault');
      }
    };
    // Finish the boot serializer before supplying any T0 transitions. Its
    // clock/data activity must neither count nor raise timer flags by itself.
    advanceTo(16000n);
    assert.equal(cpu.readIO(IO.TCNT0),0,profile.id+' serializer must not clock Timer0');
    assert.equal(cpu.readIO(IO.TIFR0),0,profile.id+' no timer event before external stimulus');
    assert.equal(cpu.readIO(IO.DDRB),mask('oc0a')|mask('oc0b')|clockMask|dataMask,profile.id+' output directions leave T0 as input');
    const bootEnd=cpu.state().baseHalf;
    for(let pulse=0;pulse<4;pulse++){
      const at=bootEnd+4096n+BigInt(pulse)*80000n;
      cpu.injectPins({at,mask:t0Mask,levels:t0Mask});
      cpu.injectPins({at:at+40000n,mask:t0Mask,levels:0});
    }
    advanceTo(bootEnd+4096n+320000n);
    const rate=config.clock.nominalOscillatorHz*2;
    const levels=value=>[clockMask,dataMask,t0Mask,1,2].map(bit=>Number(!!(value&bit)));
    const csv='time_s,clock,data,t0,oc0a,oc0b\n0,0,0,0,0,0\n'+
      events.map(event=>[Number(event.baseHalf)/rate,...levels(event.levels)].join(',')).join('\n')+'\n';
    const csvPath=join(out,profile.id+'.csv'),tracePath=join(out,profile.id+'.json');
    const smokeConfig=join(out,profile.id+'-config.json');
    writeFileSync(csvPath,csv);
    writeFileSync(smokeConfig,JSON.stringify({...config,profiles:[{...profile,pulses:4}]}));
    run(options['--python']??process.env.PYTHON??'python',[join(folder,'timer0-top-zero-probe-decode.py'),csvPath,
      '--config',smokeConfig,'--source',source,'--profile',profile.id,'--capture-kind','synthetic','-o',tracePath]);
    const trace=JSON.parse(readFileSync(tracePath,'utf8'));
    assert.equal(trace.status,'synthetic-decoder-test');
    assert.equal(trace.measurements.sourceSha256,hash(source),'Decoder must identify the actual assembled source');
    const boot=trace.records[0],samples=trace.records.slice(1);
    assert.equal(boot.tcnt0,0);assert.equal(boot.tifr0,0);assert.equal(boot.pinb&t0Mask,0);
    assert.deepEqual(samples.map(sample=>sample.tcnt0),controls.get(profile.id),profile.id+' documented counter sequence');
    for(const sample of trace.records){
      assert.equal(sample.ocr0a,profile.defines.PROBE_INITIAL_TOP);
      assert.equal(sample.ocr0b,profile.defines.PROBE_OCR0B);
      assert.equal(sample.tccr0a,(profile.defines.PROBE_COM0A<<6)|(profile.defines.PROBE_COM0B<<4)|1);
      assert.equal(sample.tccr0b,((profile.defines.PROBE_MODE&4)<<1)|7);
      if(sample.type===1)assert.equal(sample.pinb&t0Mask,t0Mask,'T0 must be high when the firmware samples it');
    }
    record.softwareControl={status:'synthetic-decoder-test',pulses:4,counters:samples.map(sample=>sample.tcnt0),
      bootTimerCount:boot.tcnt0,bootFlags:boot.tifr0,pinEvents:events.length,captureSha256:hash(csvPath),
      translatedWasmSha256:hashBytes(cpu.transpiledBytes),translatedWasmBytes:cpu.transpiledBytes.length,
      translationManifestSha256:hashBytes(JSON.stringify(cpu.transpilation))};
  }
  profiles.push(record);
}
assert.equal(profiles.filter(profile=>profile.softwareControl).length,controls.size,'Execute every nonzero control');
const result={schema:'micromusic-attiny13a-timer0-probe-verification-v1',status:'software-verification-only',
  verificationScriptSha256:hash(fileURLToPath(import.meta.url)),
  decoderSha256:hash(join(folder,'timer0-top-zero-probe-decode.py')),
  sourceSha256:hash(source),configurationSha256:hash(configPath),atdfSha256:hash(atdfPath),
  generatedDefinitionsSha256:hash(join(folder,'../attiny13a-registers.generated.inc')),
  runtimeSha256:hash(join(root,'web-player/wasm/attiny13a.wasm')),
  librarySourceSha256:librarySources,
  toolchain:avr('avr-gcc',['--version']).split(/\r?\n/)[0],node:process.version,profiles,
  expectedSiliconTrace:null};
writeFileSync(join(out,'summary.json'),JSON.stringify(result,null,2)+'\n');
console.log(`Built ${profiles.length} profiles (${Math.min(...profiles.map(p=>p.bytes))}–${Math.max(...profiles.map(p=>p.bytes))} bytes); ${controls.size} nonzero software controls passed. No silicon results.`);
console.log(join(out,'summary.json'));
