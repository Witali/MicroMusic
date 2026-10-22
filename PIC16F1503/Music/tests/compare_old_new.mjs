import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {PIC16F1503 as New,readPIC16Hex} from '../web/pic16-core.mjs';
import {PIC16F1503 as Old} from '../../PIC16F1503_timing_audit_v2/web/pic16-core.mjs';
const image=fs.readFileSync(new URL('../firmware/micromusic_with_config.hex',import.meta.url),'utf8');
const rom=readPIC16Hex(image),target=Number(process.argv[2]||8000);
const result={};
for(const [name,Core] of [['old',Old],['patched',New]]){
 const sim=new Core(rom);let i=0;
 while(sim.samples.length<target){sim.step();if(++i>10_000_000)throw Error('Not reaching PWM target');}
 const bytes=Buffer.from(sim.samples.slice(0,target));
 result[name]={cycles:sim.cycle, instructions:i, irq:sim.irqCount,pwmPeriods:sim.pwmPeriodCount,
  pc:sim.PC,underruns:sim.mem[0x60], sha256:createHash('sha256').update(bytes).digest('hex')};
 if(name==='old')result.baselineBytes=bytes; else result.samePWM=bytes.equals(result.baselineBytes);
}
delete result.baselineBytes;
fs.writeFileSync(new URL('../reports/compare_original.json',import.meta.url),JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result,null,2));
if(!result.samePWM)process.exitCode=1;
