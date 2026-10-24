// Source-only hardware probes: build every variant and exercise explicit
// software fixtures. These checks never supply silicon observations.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {closeSync,existsSync,mkdirSync,openSync,readFileSync,readdirSync,writeFileSync,writeSync} from 'node:fs';
import {dirname,join,relative,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {ATtiny13A} from '../lib/attiny13a.js';
import {AT13_IO as IO,AT13_MASK as MASK} from '../lib/attiny13a-registers.js';

const root=fileURLToPath(new URL('../../',import.meta.url)),args=process.argv.slice(2),options={};
while(args.length){
  const name=args.shift();
  if(!['--probe','--out','--avr-bin','--python'].includes(name)||!args.length)throw Error('Usage: verify-hardware-probes.mjs [--probe clkpr|reset|adc] [--out DIR] [--avr-bin DIR] [--python FILE]');
  options[name]=args.shift();
}
const names=options['--probe']?[options['--probe']]:['clkpr','reset','adc'];
assert.ok(names.every(name=>['clkpr','reset','adc'].includes(name)),'Unknown probe');
const folder=join(root,'web-player/native/peripherals');
const out=resolve(options['--out']??join(root,'build/hardware-probe-verification'));
mkdirSync(out,{recursive:true});
const suffix=process.platform==='win32'?'.exe':'';
let avrBin=options['--avr-bin']&&resolve(options['--avr-bin']);
if(!avrBin)for(let path=root;;path=dirname(path)){
  const candidate=join(path,'build/toolchains/avr-7.3.0/bin');
  if(existsSync(join(candidate,'avr-gcc'+suffix))){avrBin=candidate;break;}
  if(path===dirname(path))break;
}
assert.ok(avrBin,'Supply --avr-bin pointing to AVR GCC/objcopy/size');
const run=(program,args)=>{
  const result=spawnSync(program,args,{cwd:root,encoding:'utf8'});
  if(result.error)throw result.error;
  assert.equal(result.status,0,result.stderr||result.stdout||program+' failed');
  return result.stdout.trim();
};
const avr=(name,args)=>run(join(avrBin,name+suffix),args);
const hashBytes=bytes=>createHash('sha256').update(bytes).digest('hex');
const hash=path=>hashBytes(readFileSync(path));
const librarySourceSha256={};
const scan=path=>{
  for(const entry of readdirSync(path,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))){
    const file=join(path,entry.name);
    if(entry.isDirectory())scan(file);
    else if(entry.isFile()&&entry.name.endsWith('.js'))librarySourceSha256[relative(root,file).replaceAll('\\','/')]=hash(file);
  }
};
scan(join(root,'web-player/lib'));
const atdf=readFileSync(join(root,'web-player/vendor/microchip/ATtiny_DFP/3.4.278/atdf/ATtiny13A.atdf'),'utf8');
// This ATDF supplies Timer/ADC mux signals but omits CLKI/RESET pad signals.
// Their PB3/PB5 roles are checked against DS40002307A Figure1-1/Table10-3 in
// the acquisition documents; do not pretend they are present in the XML.
assert.match(atdf,/<signal[^>]*group="OCA"[^>]*pad="PB0"/,'Manufacturer OC0A mapping');

function exercise(name,config,profile,binary,directory){
  const fuses={...config.fuses,...profile.fuses};
  const cpu=new ATtiny13A(binary,null,{resumable:true,fastIdle:false,oscillatorHz:config.clock.frequencyHz,
    vccMicrovolts:5000000,watchdogHz:128000,fuseLow:Number(fuses.low),fuseHigh:Number(fuses.high),lock:Number(fuses.lock),
    fuseStartupProfile:1,adcFirstSample:27,
    clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}});
  const half=500000000000n/BigInt(config.clock.frequencyHz),quantum=half*128n;
  const limit=name==='clkpr'?2000000000000n:name==='reset'?250000000000n:25000000000n;
  assert.equal(cpu.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:half,lowPs:half,
    transitionCount:limit/half,knownUntilPs:limit}),true);
  if(name==='adc')cpu.setAnalogPs({at:0n,pin:2,microvolts:1000000});
  const pin=role=>1<<Number(config.pins[role].match(/^PB([0-5])$/)[1]);
  assert.equal(pin('clki'),MASK.PINB3);
  const clock=pin('clock'),marker=config.pins.marker?pin('marker'):0,oc=config.pins.oc0a?pin('oc0a'):0;
  const columns=[...new Set(['time_s',...config.requiredCsvColumns])];
  const csv=join(directory,profile.id+'.csv'),fd=openSync(csv,'w');
  let buffer=columns.join(',')+'\n',previous=cpu.state().pins.levels,bitCount=0,lastSource=null,sourceEdges=0;
  const ocEdges=[],markerEdges=[],runningEdges=[],heartbeatEdges=[],frameEnds=[];
  const emit=(at,levels)=>{
    const row=columns.map(column=>{
      if(column==='time_s')return Number(at)/1e12;
      if(column==='vcc')return 5;
      if(column==='adc1')return 1; // Declared ideal constant software stimulus.
      if(column==='reset')return (levels&pin('reset'))?5:0;
      return Number(!!(levels&pin(column)));
    });
    buffer+=row.join(',')+'\n';
    if(buffer.length>=65536){writeSync(fd,buffer);buffer='';}
  };
  emit(0n,previous);
  const consume=()=>{
    for(const event of cpu.drainPinsPs()){
      const changed=previous^event.levels,at=event.timePs;
      if((changed&clock)&&(event.levels&clock)){bitCount++;if(!(bitCount%112))frameEnds.push(at);}
      if(changed&MASK.PINB3){
        if(at>0n){if(lastSource!==null)assert.equal(at-lastSource,half,'Continuous source phases');lastSource=at;sourceEdges++;}
      }
      if(changed&oc)ocEdges.push(at);
      if(changed&marker)markerEdges.push({at,high:!!(event.levels&marker)});
      if(name==='reset'&&(changed&pin('running')))runningEdges.push({at,high:!!(event.levels&pin('running')),driven:!!(event.driven&pin('running'))});
      if(name==='reset'&&(changed&pin('heartbeat')))heartbeatEdges.push(at);
      previous=event.levels;emit(at,event.levels);
    }
  };
  consume();
  const advance=end=>{
    while(cpu.state().timePs<end){
      const now=cpu.state().timePs;
      cpu.runUntilPs(now+quantum<end?now+quantum:end);consume();
      assert.equal(cpu.state().deviceFault,0,profile.id+' native fault');
      assert.ok(cpu.state().timePs>now,'Source execution must progress');
    }
  };
  const frames=count=>{
    while(bitCount<count*112){
      const now=cpu.state().timePs;
      assert.ok(now+quantum<=limit,profile.id+' complete-frame deadline');
      advance(now+quantum);
    }
    // A fixed source slice is shorter than even one CPU cycle at /256.
    // Finish the serializer/RET in CPU clocks before inspecting idle levels.
    const finish=half*2n*BigInt(cpu.state().clockDivisor)*32n;
    advance(cpu.state().timePs+(finish>quantum?finish:quantum));
    assert.equal(cpu.state().pins.levels&clock,0,'Complete frame returns trace clock low');
  };
  let resetControl=null;
  try{
    if(name==='reset'){
      frames(1);
      advance(cpu.state().timePs+half*4096n*BigInt(cpu.state().clockDivisor));
      assert.ok(heartbeatEdges.length>=2,'Heartbeat executes after boot');
      assert.ok(heartbeatEdges.every(at=>at>frameEnds[0]),'No heartbeat before the complete boot frame');
      const assertAt=cpu.state().timePs+half*32n,releaseAt=assertAt+10000000n;
      cpu.injectPinsPs({at:assertAt,mask:MASK.PINB5,levels:0});
      cpu.injectPinsPs({at:releaseAt,mask:MASK.PINB5,levels:MASK.PINB5});
      advance(assertAt+5000000n);
      assert.equal(cpu.state().resetHeld,true);
      assert.equal(cpu.state().pins.driven&pin('running'),0,'RESET releases the running output');
      frames(2);
      assert.equal(cpu.state().resetCount,1);
      assert.ok(runningEdges.some(event=>event.at===assertAt&&!event.high&&!event.driven));
      assert.ok(runningEdges.some(event=>event.at>releaseAt&&event.high&&event.driven));
      resetControl={assertPs:assertAt.toString(),releasePs:releaseAt.toString(),kind:'prequalified-digital-software-input'};
    }else frames(config.expectedRecords);
  }finally{if(buffer)writeSync(fd,buffer);closeSync(fd);}
  const tracePath=join(directory,profile.id+'.json');
  run(options['--python']??process.env.PYTHON??'python',[join(folder,'hardware-probe-decode.py'),csv,
    '--config',join(folder,name+'-probe.json'),'--profile',profile.id,'--source',join(folder,config.firmware),
    '--capture-kind','synthetic','-o',tracePath]);
  const trace=JSON.parse(readFileSync(tracePath,'utf8')),records=trace.records;
  assert.equal(trace.status,'synthetic-decoder-test');assert.equal(trace.transportQuality,'complete-frames');
  assert.equal(trace.identities.sourceSha256,hash(join(folder,config.firmware)));
  if(name==='clkpr'){
    const initial=profile.defines.PROBE_INITIAL_DIV,requested=profile.defines.PROBE_FINAL_DIV,kind=profile.defines.PROBE_WRITE_KIND;
    const final=kind===0?requested:initial;
    assert.equal(records.length,2);
    for(const [index,record] of records.entries())assert.deepEqual(record.data,[kind,initial,requested,index?final:initial,0x42,1]);
    assert.deepEqual(markerEdges.map(event=>event.high),[true,false]);
    const before=ocEdges.filter(at=>at<markerEdges[0].at).slice(-20);
    const after=ocEdges.filter(at=>at>markerEdges[1].at).slice(-20);
    for(const [edges,code] of [[before,initial],[after,final]]){
      assert.equal(edges.length,20);
      for(let i=1;i<edges.length;i++)assert.equal(edges[i]-edges[i-1],half*2n*(1n<<BigInt(code)),'CTC output observes steady clkI/O');
    }
  }else if(name==='reset'){
    assert.equal(records.length,2);
    const div=Number(fuses.low)&16?0:3;
    for(const [index,record] of records.entries()){
      assert.equal(record.data[0],index?MASK.EXTRF:MASK.PORF);
      assert.equal(record.data[1],div);assert.equal(record.data[3],0x17);
      assert.equal(record.data[4],1);assert.equal(record.data[5],0);
    }
  }else{
    assert.equal(records.length,3);assert.equal(records[0].data[5],0);
    assert.equal(records[0].data[1],1);assert.equal(records[0].data[2],0);assert.equal(records[0].data[3],MASK.ADC1D);
    assert.deepEqual(markerEdges.map(event=>event.high),[true,false,true,false]);
    for(const record of records.slice(1)){
      assert.equal(record.data[0]|record.data[1]<<8,204,'ADC1/PB2 constant 1V at ideal 5V reference');
      assert.equal(record.data[4]&128,0);assert.equal(record.data[3]&MASK.ADSC,0);
      if(profile.defines.PROBE_MODE===2){
        assert.equal(record.data[2]&MASK.ADIF,MASK.ADIF);assert.equal(record.data[2]&MASK.ADSC,0);
        const op=profile.defines.PROBE_ADIF_OPERATION;
        if([0,4].includes(op))assert.equal(record.data[3]&MASK.ADIF,MASK.ADIF);
        if([5,6].includes(op))assert.equal(record.data[3]&MASK.ADIF,0);
        // SBI/CBI ADIF results are recorded under the configured software
        // policy; they are the very hardware ambiguity this probe must measure.
      }
    }
  }
  return {status:'synthetic-decoder-test',records:records.map(({sequence,data})=>({sequence,data})),
    timePs:cpu.state().timePs.toString(),sourceEdges,traceSha256:hash(tracePath),waveformSha256:hash(csv),resetControl,
    translatedWasmSha256:hashBytes(cpu.transpiledBytes),translatedWasmBytes:cpu.transpiledBytes.length,
    translationManifestSha256:hashBytes(JSON.stringify(cpu.transpilation))};
}

const probes=[];
for(const name of names){
  const configPath=join(folder,name+'-probe.json'),config=JSON.parse(readFileSync(configPath,'utf8'));
  assert.equal(config.schema,'micromusic-attiny13a-hardware-probe-v1');assert.equal(config.expectedSiliconTrace,null);
  assert.equal(config.status,'pending-hardware');assert.equal(config.wire.version,2);
  assert.equal(config.fields.length,6);assert.equal(config.pins.clki,'PB3');assert.equal(config.pins.reset,'PB5');
  if(name==='clkpr')assert.equal(config.pins.oc0a,'PB0');
  if(name==='adc')assert.equal(config.pins.analogInput,'PB2');
  if(name==='reset'){assert.equal(config.pins.running,'PB0');assert.equal(config.pins.heartbeat,'PB1');}
  assert.equal(new Set(Object.values(config.pins)).size,6,'Probe pin roles must not overlap');
  const directory=join(out,name);mkdirSync(directory,{recursive:true});
  const profiles=[];
  for(const profile of config.profiles){
    assert.match(profile.id,/^[a-z0-9-]+$/);assert.equal(profile.defines.PROBE_PROFILE_ID,profile.profileId);
    const elf=join(directory,profile.id+'.elf'),image=join(directory,profile.id+'.bin');
    avr('avr-gcc',['-mmcu=attiny13a','-nostdlib','-nostartfiles','-Wall','-Wextra','-Werror','-Wl,--gc-sections','-Wl,-e,__vectors',
      ...Object.entries(profile.defines).map(([key,value])=>'-D'+key+'='+value),join(folder,config.firmware),'-o',elf]);
    avr('avr-objcopy',['-O','binary','-j','.text',elf,image]);
    const size=avr('avr-size',[elf]).split(/\r?\n/).at(-1).trim().split(/\s+/).slice(0,3).map(Number);
    const binary=readFileSync(image);assert.equal(binary.length,size[0]);assert.ok(binary.length<=1024);assert.deepEqual(size.slice(1),[0,0]);
    const software=exercise(name,config,profile,binary,directory);
    profiles.push({id:profile.id,profileId:profile.profileId,defines:profile.defines,fuses:{...config.fuses,...profile.fuses},
      bytes:binary.length,imageSha256:hash(image),software});
    console.log(`${name}/${profile.id}: ${binary.length} bytes; source/CPU/transport software control passed`);
  }
  probes.push({name,sourceSha256:hash(join(folder,config.firmware)),configurationSha256:hash(configPath),profiles});
}
const summary={schema:'micromusic-attiny13a-hardware-probe-verification-v1',status:'software-verification-only',
  verificationScriptSha256:hash(fileURLToPath(import.meta.url)),wireSha256:hash(join(folder,'probe-wire.inc')),
  decoderSha256:hash(join(folder,'hardware-probe-decode.py')),registerDefinitionsSha256:hash(join(folder,'../attiny13a-registers.generated.inc')),
  runtimeSha256:hash(join(root,'web-player/wasm/attiny13a.wasm')),librarySourceSha256,
  toolchain:avr('avr-gcc',['--version']).split(/\r?\n/)[0],node:process.version,
  fixture:{source:'digital-noninverting-zero-seed-v1',initialLevel:1,fuseStartupProfile:1,
    vccMicrovolts:5000000,watchdogHz:128000,adc1Microvolts:1000000,adcFirstSample:27,sourceHalfCyclesPerDrain:128,
    resetInput:'prequalified digital; no analog threshold/RC claim'},probes,expectedSiliconTrace:null};
writeFileSync(join(out,'summary.json'),JSON.stringify(summary,null,2)+'\n');
console.log(`Verified ${probes.reduce((n,probe)=>n+probe.profiles.length,0)} source-only profiles; no silicon observations.`);
console.log(join(out,'summary.json'));
