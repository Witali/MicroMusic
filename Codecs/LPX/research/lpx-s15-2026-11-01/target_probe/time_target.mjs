import {readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
if(!process.argv[2]||!process.argv[3])throw Error('Usage: node time_target.mjs OUTPUT_DIR REPO_ROOT');
const root=resolve(process.argv[2]);
const engine=resolve(process.argv[3],'web-player/lib/avr-transpiled.js');
const sha=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
const engineHash=sha(engine);
const {AVRCore}=await import(pathToFileURL(engine));
const nm=readFileSync(root+'/s15-direct.nm','utf8');
const sym=name=>{const r=nm.split(/\r?\n/).find(r=>r.trim().endsWith(' '+name));if(!r)throw Error('Missing marker');return parseInt(r.trim().split(/\s+/)[0],16)&65535;};
const done=sym('probe_done'),pcm=sym('probe_pcm'),err=sym('probe_error'),count=sym('probe_samples'),bssEnd=sym('__bss_end');
const options={target:'attiny88',cpuHz:16000000,fastIdle:false,fastBlocks:false,optimizeFlags:false,cacheTranslation:false};
const binary=root+'/s15-direct.bin',binaryHash=sha(binary);
const cpu=new AVRCore(readFileSync(binary),null,options);
const output=[],cycles=[];let instructions=0;const begin=performance.now();
while(!cpu.data[done]){
 if(cpu.cyc>400000000)throw Error('Cycle bound exceeded');
 const sample=cpu.op[cpu.pc]===38&&cpu.k[cpu.pc]===pcm;
 cpu.step();instructions++;
 if(sample){output.push(cpu.data[pcm]);cycles.push(cpu.cyc);}
 if(cpu.minSP<bssEnd)throw Error('Stack collided with static RAM');
}
const samples=cpu.data[count]|cpu.data[count+1]<<8;
if(samples!==19200||output.length!==samples||cpu.data[err])throw Error('Incomplete decode');
const actual=Buffer.from(output),expected=readFileSync(root+'/actual-m1-expected.pwm');
if(!actual.equals(expected))throw Error('Target/native complete PWM differs');
if(sha(engine)!==engineHash||sha(binary)!==binaryHash)throw Error('Measured source/image changed');
let maxGap=0;for(let i=1;i<cycles.length;i++)maxGap=Math.max(maxGap,cycles[i]-cycles[i-1]);
const result={status:'PASS',image_kind:'unpaced-test-image',target:'attiny88',engine:'existing-avr-transpiled',
 engine_sha256:engineHash,binary_sha256:binaryHash,options,samples,instructions,total_cycles:cpu.cyc,
 cycles_per_sample:cpu.cyc/samples,required_cycles_per_sample_at_8khz:2000,
 first_output_cycle:cycles[0],last_output_cycle:cycles.at(-1),maximum_inter_output_cycles:maxGap,
 min_sp:cpu.minSP,bss_end:bssEnd,observed_stack_bytes:767-cpu.minSP,
 observed_stack_margin_bytes:cpu.minSP-bssEnd,irq_enabled:false,irq_count:cpu.irqCount,
 full_pwm_native_exact:true,supported_8khz_profile:false,host_wall_seconds:(performance.now()-begin)/1000};
writeFileSync(root+'/s15-direct-unpaced.pwm',actual);
writeFileSync(root+'/target-timing-private.json',JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result));
