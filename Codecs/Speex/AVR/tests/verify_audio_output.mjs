// Compile and exercise the common hardware routing without executing a decoder.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {dirname,join,resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {CPU,avrInstruction,AVRTimer,timer1Config,timer2Config,AVRIOPort,portBConfig,portDConfig} from 'avr8js';
import {tickAvr} from './avr_tick.mjs';
const root=fileURLToPath(new URL('../',import.meta.url)),gcc=resolve(process.argv[2]);
const out=resolve(process.argv[3]||join(root,'build/audio-output'));mkdirSync(out,{recursive:true});
const tool=name=>join(dirname(gcc),'avr-'+name+(gcc.endsWith('.exe')?'.exe':''));
const options=['-std=c11','-mmcu=atmega328p','-Os','-I'+join(root,'src')];
const results=[];
for(const pin of [3,9])for(const hz of [8000,16000]){
  const name=join(out,`d${pin}-${hz}`),elf=name+'.elf',bin=name+'.bin';
  execFileSync(gcc,[...options,`-DSPEEX_AVR_PWM_PIN=${pin}`,`-DSPEEX_AUDIO_SAMPLE_HZ=${hz}`,join(root,'tests/audio_output_probe.c'),'-o',elf]);
  execFileSync(tool('objcopy'),['-O','binary','-R','.eeprom',elf,bin]);
  const symbols=new Map(execFileSync(tool('nm'),['-n',elf],{encoding:'utf8'}).split(/\r?\n/).map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
  const bytes=readFileSync(bin),program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(bytes);
  const cpu=new CPU(program,2048),b=new AVRIOPort(cpu,portBConfig),d=new AVRIOPort(cpu,portDConfig);
  new AVRTimer(cpu,timer1Config);new AVRTimer(cpu,timer2Config);
  const cfg=pin===3?portDConfig:portBConfig,bit=pin===3?3:1,port=pin===3?d:b;
  const pwmAddress=pin===3?timer2Config.OCRB:timer1Config.OCRA;
  const times=[],values=[],rises=[],widths=[];let rise,wasHigh=false;
  port.addListener(value=>{
    const high=Boolean(value&(1<<bit));
    if(high&&!wasHigh){rises.push(cpu.cycles);rise=cpu.cycles;}
    if(!high&&wasHigh&&rise!==undefined)widths.push(cpu.cycles-rise);
    wasHigh=high;
  });
  const previous=cpu.writeHooks[pwmAddress];
  cpu.writeHooks[pwmAddress]=(v,old,at,mask)=>{
    if(cpu.data[symbols.get('probe_started')]){times.push(cpu.cycles);values.push(v);}
    return previous?.(v,old,at,mask)??false;
  };
  while(!cpu.data[symbols.get('probe_done')]){
    assert.ok(cpu.cycles<32*(16000000/hz)+10000);
    const enabled=cpu.interruptsEnabled;avrInstruction(cpu);tickAvr(cpu,enabled);
  }
  assert.deepEqual(values,Array.from({length:32},(_,i)=>32+(i&3)*48));
  assert.equal(cpu.data[cfg.DDR],1<<bit);
  assert.equal(cpu.data[(pin===3?portBConfig:portDConfig).DDR],0);
  const intervals=times.slice(1).map((t,i)=>t-times[i]),period=16000000/hz;
  assert.ok(intervals.every(v=>Math.abs(v-period)<=8),'PCM timer/IRQ period');
  const carrier=rises.slice(2).map((t,i)=>t-rises[i+1]);
  // Clock events are observed at instruction/IRQ boundaries in AVR8js, not
  // sub-instruction GPIO timestamps. Check the carrier mean and bounded lag.
  assert.ok(carrier.length>80&&carrier.every(v=>Math.abs(v-256)<=8),`D${pin}/${hz} carrier: ${carrier.length} periods, ${Math.min(...carrier)}..${Math.max(...carrier)} cycles`);
  assert.ok(Math.abs(carrier.reduce((a,b)=>a+b,0)/carrier.length-256)<0.1);
  assert.ok(widths.some(v=>v<70)&&widths.some(v=>v>160),'PWM duty changes reach the pin');
  results.push({pin,sampleHz:hz,outputs:values.length,pcmMinCycles:Math.min(...intervals),pcmMaxCycles:Math.max(...intervals),
    carrierMinCycles:Math.min(...carrier),carrierMaxCycles:Math.max(...carrier),binarySha256:createHash('sha256').update(bytes).digest('hex')});
}
for(const bad of ['-DSPEEX_AVR_PWM_PIN=4','-DF_CPU=8000000UL']){
  assert.throws(()=>execFileSync(gcc,[...options,'-DSPEEX_AUDIO_SAMPLE_HZ=8000',bad,join(root,'tests/audio_output_probe.c'),'-o',join(out,'invalid.elf')],{stdio:'pipe'}));
}
const hash=p=>createHash('sha256').update(readFileSync(join(root,p)).toString().replace(/\r\n/g,'\n')).digest('hex');
const report={passed:true,simulator:'avr8js 0.21.1',compiler:execFileSync(gcc,['-dumpversion'],{encoding:'utf8'}).trim(),
  scope:'Hardware routing only; real timer IRQ and GPIO carrier; no decoder execution',physicalBoardTested:false,
  sourceSha256:Object.fromEntries(['src/avr_audio_output.h','tests/audio_output_probe.c','tests/verify_audio_output.mjs','tests/avr_tick.mjs'].map(p=>[p,hash(p)])),results};
writeFileSync(join(out,'verification.json'),JSON.stringify(report,null,2)+'\n');
console.log('PASS D3/D9 hardware routing, 8/16 kHz PCM, 62.5 kHz GPIO PWM, invalid settings rejected');
