// Executes actual AVR acquisition images. Outputs are software controls only.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {closeSync,existsSync,mkdirSync,openSync,readFileSync,readdirSync,writeFileSync,writeSync} from 'node:fs';
import {dirname,join,relative,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {ATtiny13A} from '../lib/attiny13a-runtime.js';

const root=fileURLToPath(new URL('../../',import.meta.url)),args=process.argv.slice(2),options={};
while(args.length){const key=args.shift();
  if(!['--profile','--out','--avr-bin','--python','--cuts'].includes(key)||!args.length)
    throw Error('Usage: verify-cpu-phase-probe.mjs [--profile ID] [--cuts boundaries|none] [--out DIR] [--avr-bin DIR] [--python FILE]');
  options[key]=args.shift();
}
assert.ok(['boundaries','none'].includes(options['--cuts']??'boundaries'));
const folder=join(root,'web-player/native/peripherals'),configPath=join(folder,'cpu-phase-probe.json');
const config=JSON.parse(readFileSync(configPath,'utf8'));
assert.equal(config.probeId,4);assert.equal(config.sequencePolicy,'restartable-pairs');assert.equal(config.expectedSiliconTrace,null);
const profiles=config.profiles.filter(profile=>!options['--profile']||profile.id===options['--profile']);
assert.ok(profiles.length,'Unknown CPU phase profile');
const out=resolve(options['--out']??join(root,'build/cpu-phase-probe-verification'));mkdirSync(out,{recursive:true});
let avrBin=options['--avr-bin']&&resolve(options['--avr-bin']);
const suffix=process.platform==='win32'?'.exe':'';
if(!avrBin)for(let path=root;;path=dirname(path)){
  const candidate=join(path,'build/toolchains/avr-7.3.0/bin');
  if(existsSync(join(candidate,'avr-gcc'+suffix))){avrBin=candidate;break;}
  if(path===dirname(path))break;
}
assert.ok(avrBin,'Supply --avr-bin');
let python=options['--python']??process.env.PYTHON;
if(!python)for(let path=root;;path=dirname(path)){
  const candidate=join(path,'build/toolchains/python-3.13.3',process.platform==='win32'?'python.exe':'python3');
  if(existsSync(candidate)){python=candidate;break;}if(path===dirname(path))break;
}
python??='python';
const run=(program,argv)=>{const result=spawnSync(program,argv,{cwd:root,encoding:'utf8'});
  if(result.error)throw result.error;assert.equal(result.status,0,result.stderr||result.stdout||program);return result.stdout.trim();};
const avr=(name,argv)=>run(join(avrBin,name+suffix),argv);
const sha=bytes=>createHash('sha256').update(bytes).digest('hex'),hash=path=>sha(readFileSync(path));
const librarySourceSha256={};
const scan=path=>{for(const entry of readdirSync(path,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))){
  const file=join(path,entry.name);if(entry.isDirectory())scan(file);
  else if(entry.isFile()&&entry.name.endsWith('.js'))librarySourceSha256[relative(root,file).replaceAll('\\','/')]=hash(file);
}};
scan(join(root,'web-player/lib'));
const runtimePath=join(root,'web-player/wasm/attiny13a.wasm'),runtimeBytes=readFileSync(runtimePath);
const runtimeModule=await WebAssembly.compile(runtimeBytes);
assert.deepEqual(WebAssembly.Module.imports(runtimeModule),[]);
const half=125000000n,cycle=half*2n,armAt=2000000000000n,endAt=4000000000000n;
const stringify=value=>JSON.stringify(value,(_key,item)=>typeof item==='bigint'?item.toString():item,2)+'\n';

function capture(profile,binary,directory,name,resetAt=null){
  const cpu=new ATtiny13A(binary,null,{runtimeModule,resumable:true,fastIdle:false,
    oscillatorHz:4000,watchdogHz:128000,vccMicrovolts:5000000,fuseLow:0x70,fuseHigh:255,lock:255,
    fuseStartupProfile:1,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}});
  assert.equal(cpu.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:half,lowPs:half,
    transitionCount:endAt/half,knownUntilPs:endAt}),true);
  cpu.injectPinsPs({at:0n,mask:34,levels:32});
  cpu.injectPinsPs({at:armAt,mask:34,levels:34});
  if(resetAt!==null){
    // Queued before execution, using the uncut preview's marker. No callback
    // races an already-executed instruction to schedule a reset in its past.
    cpu.injectPinsPs({at:resetAt,mask:34,levels:2});
    cpu.injectPinsPs({at:resetAt+half,mask:34,levels:0});
    cpu.injectPinsPs({at:resetAt+half*4n,mask:34,levels:32});
  }
  const csv=join(directory,name+'.csv'),fd=openSync(csv,'w');
  let previous=cpu.state().pins.levels,buffer=config.requiredCsvColumns.join(',')+'\n',sourceEdges=0;
  const markers=[];
  const emit=(at,levels)=>{buffer+=[Number(at)/1e12,Number(!!(levels&4)),Number(!!(levels&16)),
    Number(!!(levels&8)),5,Number(!!(levels&1)),Number(!!(levels&2)),levels&32?5:0].join(',')+'\n';
    if(buffer.length>=65536){writeSync(fd,buffer);buffer='';}};
  emit(0n,previous);
  const consume=()=>{for(const event of cpu.drainPinsPs()){
    const changed=previous^event.levels;
    if(changed&8)sourceEdges++;
    if(changed&1)markers.push({at:event.timePs,high:!!(event.levels&1),driven:!!(event.driven&1),beforeLevels:previous});
    emit(event.timePs,event.levels);previous=event.levels;
  }};
  try{consume();while(cpu.state().timePs<endAt){const now=cpu.state().timePs,next=now+half*128n;
    cpu.runUntilPs(next<endAt?next:endAt);consume();
    assert.equal(cpu.state().deviceFault,0,profile.id+' device fault');assert.ok(cpu.state().timePs>now);
  }}finally{if(buffer)writeSync(fd,buffer);closeSync(fd);}
  assert.equal(sourceEdges,Number(endAt/half),'Every supplied CLKI transition must remain in the physical capture');
  const decodedPath=join(directory,name+'.json');
  run(python,[join(folder,'hardware-probe-decode.py'),csv,
    '--config',configPath,'--profile',profile.id,'--capture-kind','synthetic','-o',decodedPath]);
  const decoded=JSON.parse(readFileSync(decodedPath,'utf8'));
  assert.equal(decoded.status,'synthetic-decoder-test');assert.equal(decoded.transportQuality,'complete-frames');
  assert.deepEqual(decoded.sequenceGaps,[]);
  assert.deepEqual(decoded.records.map(record=>record.sequence),resetAt===null?[0,1,2,3]:[0,1,0,1]);
  assert.equal(cpu.state().resetCount,resetAt===null?0:1);
  return {records:decoded.records.map(({sequence,data})=>({sequence,data})),markers,sourceEdges,
    waveformSha256:hash(csv),decodedSha256:hash(decodedPath),translatedSha256:sha(cpu.transpiledBytes),
    resetAtPs:resetAt,timePs:cpu.state().timePs};
}

function model(profile,symbols,elapsed=null,expectedIn=0){
  const id=profile.profileId,test=symbols.TEST_BASE,returnPC=symbols.after_target/2;
  const z=id===4?symbols.call_target/2:symbols.flash_data+(id===17?1:0);
  const memory=[0x11,0x22,0x33,0x44],registers=[0x55,0xe7,test+1,0,z&255,z>>8];
  if(id===5||id===6){memory[0]=returnPC>>8;memory[1]=returnPC&255;}
  const effect=(cycles,action)=>{if(elapsed===null||elapsed>BigInt(cycles)*cycle)action();};
  // Strict > expresses the documented digital convention: RESET wins ties.
  if(id===1)effect(2,()=>{memory[1]=0xe7;});
  if(id===2)effect(2,()=>{registers[1]=0x22;});
  if(id===3||id===4||id===7){const pc=id===7?symbols.phase_target/2:returnPC;
    effect(2,()=>{memory[1]=pc&255;});effect(3,()=>{memory[0]=pc>>8;});}
  if([8,9,10,14].includes(id))effect(2,()=>{
    registers[1]=id===10?0x11:0x22;
    if(id===9)registers[2]=test+2;if(id===10)registers[2]=test;
  });
  if([11,12,13,15].includes(id))effect(2,()=>{
    memory[id===13?0:1]=0xe7;
    if(id===12)registers[2]=test+2;if(id===13)registers[2]=test;
  });
  if([16,17,18].includes(id))effect(3,()=>{
    registers[id===16?0:1]=id===17?0x36:0xa9;
    if(id===18){registers[4]=(z+1)&255;registers[5]=(z+1)>>8;}
  });
  if(id===19)effect(1,()=>{registers[1]=expectedIn;});
  if(id===21)effect(3,()=>{memory[2]=0xe7;});
  return {memory,registers};
}

const results=[];
for(const profile of profiles){
  const directory=join(out,profile.id);mkdirSync(directory,{recursive:true});
  const elf=join(directory,'probe.elf'),image=join(directory,'probe.bin');
  avr('avr-gcc',['-mmcu=attiny13a','-nostdlib','-nostartfiles','-Wall','-Wextra','-Werror',
    '-Wl,--gc-sections','-Wl,-e,__vectors','-DPROBE_PROFILE_ID='+profile.profileId,
    join(folder,config.firmware),'-o',elf]);
  avr('avr-objcopy',['-O','binary','-j','.text',elf,image]);
  const binary=readFileSync(image);assert.ok(binary.length<=1024);
  const size=avr('avr-size',[elf]).split(/\r?\n/).at(-1).trim().split(/\s+/).slice(0,3).map(Number);
  assert.deepEqual(size,[binary.length,0,0]);
  const symbols={};
  for(const line of avr('avr-nm',['-g','--defined-only',elf]).split(/\r?\n/)){
    const match=line.match(/^([0-9a-fA-F]+)\s+\w\s+(\S+)$/);if(match)symbols[match[2]]=parseInt(match[1],16);
  }
  for(const [name,word] of [['phase_prelude',253],['phase_marker',254],['phase_target',255]])assert.equal(symbols[name],word*2,name);
  assert.ok(symbols.SNAP_BASE+12<=0x9c,'Snapshots stay below encoder stack');
  assert.equal(binary[symbols.flash_data],0xa9);assert.equal(binary[symbols.flash_data+1],0x36);
  const preview=capture(profile,binary,directory,'uncut');
  assert.deepEqual(preview.markers.map(event=>event.high),[true,false]);
  const marker=preview.markers[0].at;
  // Independent Figure10-4 convention: immediate IN after OUT sees old PB0=0
  // and the old serialized PB4 level; ARM is stable high, trace clock low,
  // PB5 digital read disabled by RESET role. Only CLKI selfread is unqualified.
  const beforeMarker=preview.markers[0].beforeLevels,expectedIn=(beforeMarker&16)|2;
  assert.equal(beforeMarker&5,0,'Old marker and trace clock are low');
  const assertRegisters=(actual,wanted,label)=>{
    const observed=[...actual],expected=[...wanted];
    if(profile.profileId===19){observed[1]&=~8;expected[1]&=~8;}
    assert.deepEqual(observed,expected,label);
  };
  const expected=model(profile,symbols,null,expectedIn);
  assert.deepEqual(preview.records[2].data,[0,0xa5,...expected.memory],profile.id+' uncut memory');
  assertRegisters(preview.records[3].data,expected.registers,profile.id+' uncut GPRs');
  const markerCycles=profile.profileId===7?7:[3,4].includes(profile.profileId)?4:
    [5,6].includes(profile.profileId)?5:[16,17,18,20,21].includes(profile.profileId)?4:
    [0,19].includes(profile.profileId)?2:3;
  assert.equal(preview.markers[1].at-marker,BigInt(markerCycles)*cycle,profile.id+' target/marker bracket');
  const cuts=[];
  if(options['--cuts']!=='none')for(const span of profile.cutHalves)for(const epsilon of [-1n,0n,1n]){
    const elapsed=BigInt(span)*half+epsilon,name=`h${span}-${epsilon<0?'before':epsilon?'after':'tie'}`;
    const trial=capture(profile,binary,directory,name,marker+elapsed),wanted=model(profile,symbols,elapsed,expectedIn);
    assert.deepEqual(trial.records[2].data,[2,0xa5,...wanted.memory],profile.id+'/'+name+' reset memory');
    assertRegisters(trial.records[3].data,wanted.registers,profile.id+'/'+name+' reset GPRs (software policy)');
    assert.ok(trial.markers.some(event=>event.at===marker+elapsed&&!event.high&&!event.driven),'Reset cancels marker drive');
    cuts.push({name,offsetPs:elapsed,...trial});
  }
  results.push({id:profile.id,profileId:profile.profileId,bytes:binary.length,imageSha256:hash(image),symbols,
    inputOracle:profile.profileId===19?{expectedMaskedPINB:expectedIn,ignoredMask:8,preMarkerPhysicalLevels:beforeMarker}:null,preview,cuts});
  console.log(`${profile.id}: ${binary.length} bytes; uncut + ${cuts.length} queued reset controls passed`);
}
const summary={schema:'micromusic-attiny13a-cpu-phase-probe-verification-v1',status:'software-verification-only',
  node:process.version,toolchain:avr('avr-gcc',['--version']).split(/\r?\n/)[0],
  identities:{sourceSha256:hash(join(folder,config.firmware)),configSha256:hash(configPath),wireSha256:hash(join(folder,'probe-wire.inc')),
    decoderSha256:hash(join(folder,'hardware-probe-decode.py')),scriptSha256:hash(fileURLToPath(import.meta.url)),
    registerDefinitionsSha256:hash(join(folder,'../attiny13a-registers.generated.inc')),
    manufacturerHeaderSha256:hash(join(root,'web-player/vendor/microchip/ATtiny_DFP/3.4.278/include/avr/iotn13a.h')),
    runtimeSha256:sha(runtimeBytes),runtimeBytes:runtimeBytes.length},
  fixture:{source:'digital-noninverting-zero-seed-v1',frequencyHz:4000,sourceHalfPs:half,armPs:armAt,endPs:endAt,
    resetInput:'prequalified digital; model RESET wins exact ties',gprResetRetention:'current software policy; hardware NOP qualification required',
    sourceHalfCyclesPerDrain:128},librarySourceSha256,profiles:results,expectedSiliconTrace:null};
writeFileSync(join(out,'summary.json'),stringify(summary));
console.log(`Verified ${results.length} acquisition profiles. No silicon observations. ${join(out,'summary.json')}`);
