import fs from 'node:fs';
import {PIC16F1503,readPIC16Hex} from '../PIC16F1503_timing_audit_v2/web/pic16-core.mjs';
const words=readPIC16Hex(fs.readFileSync(new URL('../PIC16F1503_timing_audit_v2/firmware/micromusic_with_config.hex',import.meta.url),'utf8'));
const cpu=new PIC16F1503(words);
const secs=14, start=Date.now(), target=secs*4_000_000;
let stackMax=0;
while(cpu.cycle < target) {
  cpu.step();
  if(cpu.stack.length>stackMax)stackMax=cpu.stack.length;
  if(cpu.mem[0x60]!==0) throw Error(`PWM queue underflow at cycle=${cpu.cycle}`);
  if(cpu.samples.length>256) cpu.samples.length=0;
}
const results={kind:'INTERNAL JS EMULATOR ONLY; NOT MPLAB SIM',simulatedSeconds:cpu.cycle/4e6,elapsedWallSeconds:(Date.now()-start)/1000,pwmInterrupts:cpu.irqCount,pwmQueueUnderruns:cpu.mem[0x60],hardwareStackMax:stackMax,PR2:cpu.mem[0x1b],outputState:cpu.mem[0x619]};
fs.writeFileSync(new URL('local_14s_results.json',import.meta.url),JSON.stringify(results,null,2)+'\n');
console.log(JSON.stringify(results,null,2));
