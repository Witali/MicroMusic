import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {dirname,join,parse,resolve} from 'node:path';
import {parseArgs} from 'node:util';
import {coreProbeCases} from './lib/avr-core-probe-cases.mjs';
const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{'out-dir':{type:'string',default:'build/probes/avr88-core'},'avr-bin':{type:'string'},nonce:{type:'string',default:'core-v1'}}});
assert.match(values.nonce,/^[a-zA-Z0-9_-]{1,64}$/);
const out=resolve(root,values['out-dir']);mkdirSync(out,{recursive:true});
let bin=values['avr-bin'];
for(let p=root;!bin;p=dirname(p)){const candidate=join(p,'build/toolchains/avr-7.3.0/bin');if(existsSync(join(candidate,'avr-gcc.exe')))bin=candidate;if(p===parse(p).root)break;}
assert.ok(bin,'Pass --avr-bin for the prepared AVR toolchain');
const run=(tool,args)=>{const r=spawnSync(join(bin,tool+(process.platform==='win32'?'.exe':'')),args,{cwd:root,encoding:'utf8'});if(r.error)throw r.error;assert.equal(r.status,0,r.stderr||r.stdout);return r.stdout;};
const sha=b=>createHash('sha256').update(b).digest('hex');
const vendor='web-player/vendor/microchip/ATtiny_DFP/3.4.278',header=vendor+'/include/avr/iotn88.h';
const provenance=JSON.parse(readFileSync(join(root,vendor,'provenance.json')));assert.equal(sha(readFileSync(join(root,header))),provenance.files['include/avr/iotn88.h'].sha256);
const source='web-player/native/devices/attiny88/core-probe.c',caseSource='web-player/scripts/lib/avr-core-probe-cases.mjs';
const sources=Object.fromEntries([source,caseSource,'web-player/scripts/build-avr-core-probe.mjs',header].map(p=>[p,sha(readFileSync(join(root,p),'utf8').replaceAll('\r\n','\n'))]));
const compilerVersion=run('avr-gcc',['--version']).split(/\r?\n/)[0];
const buildId=Array.from(Buffer.from(sha(JSON.stringify({sources,nonce:values.nonce,compilerVersion})).slice(0,8),'hex'));
function measure(name,c){
    const lines=[`ldi r16,${c.a}`,`ldi r17,${c.b}`,c.setup||'',`ldi r18,${c.flags}`,'out %[sreg],r18','lds r8,%[timerL]','lds r9,%[timerH]',c.asm||'',
      'in r19,%[sreg]','lds r10,%[timerL]','lds r11,%[timerH]','sub r10,r8','sbc r11,r9','st %a[dest]+,r16','st %a[dest]+,r19','st %a[dest]+,r10','st %a[dest]+,r11'].filter(Boolean);
    return `static void ${name}(uint8_t *out){__asm__ __volatile__(\n${JSON.stringify(lines.join('\n\t')+'\n')}\n: [dest] "+e" (out) : [sreg] "I" (_SFR_IO_ADDR(SREG)), [timerL] "n" (_SFR_MEM_ADDR(TCNT1L)), [timerH] "n" (_SFR_MEM_ADDR(TCNT1H)) : "r8","r9","r10","r11","r16","r17","r18","r19","r24","r25","memory","cc");}\n`;
}
let generated='#include <stdint.h>\n#include <avr/io.h>\n#include <avr/pgmspace.h>\nextern volatile uint8_t probe_packet[64];\n';
generated+=`#define PROBE_CASE_COUNT ${coreProbeCases.length}\nstatic const uint8_t probe_build_id[4] PROGMEM={${buildId}};\n`;
generated+=`static const uint8_t probe_expected[PROBE_CASE_COUNT][3] PROGMEM={${coreProbeCases.map(c=>`{${c.result},${c.sreg},${c.cycles}}`).join(',')}};\n`;
generated+=measure('probe_control',{a:0,b:0,flags:0});
coreProbeCases.forEach((c,n)=>generated+=measure('probe_case_'+n,c));
generated+='static void probe_run_cases(uint8_t *out){'+coreProbeCases.map((_,n)=>`probe_case_${n}(out+${4*n});`).join('')+'}\n';
writeFileSync(join(out,'probe-cases.generated.h'),generated);
const elf=join(out,'probe.elf'),flags=['-mmcu=attiny88','-DF_CPU=16000000UL','-Os','-std=gnu11','-Wall','-Wextra','-Werror',
  '-I'+join(root,vendor,'include'),'-I'+out,'-Wl,-Map='+join(out,'probe.map')];
run('avr-gcc',[...flags,join(root,source),'-o',elf]);
run('avr-objcopy',['-O','ihex','-R','.eeprom',elf,join(out,'probe.hex')]);run('avr-objcopy',['-O','binary','-R','.eeprom',elf,join(out,'probe.bin')]);
const binary=readFileSync(join(out,'probe.bin'));assert.ok(binary.length<=6012,'Micronucleus application limit');
const symbols=Object.fromEntries(run('avr-nm',['-n',elf]).split(/\r?\n/).map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(\S+)$/i)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
assert.ok(Number.isInteger(symbols.probe_complete));
assert.ok(Number.isInteger(symbols.probe_measured));
const report={schema:'micromusic-avr-core-probe-v1',device:'ATtiny88',board:'mh-et-live-16mhz',nominalCpuHz:16000000,
  hardwareTested:false,buildId,nonce:values.nonce,cases:coreProbeCases,compilerVersion,flags,sources,symbols,
  flashBytes:binary.length,flashSha256:sha(binary),eepromBytesWritten:64,resultFormat:'AVR1/64-byte/CRC16-CCITT',
  vendor:{package:provenance.package,version:provenance.version,sourceUrl:provenance.sourceUrl,headerSha256:sha(readFileSync(join(root,header)))}};
writeFileSync(join(out,'descriptor.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({out,bytes:binary.length,flashSha256:report.flashSha256,buildId,measuredPC:symbols.probe_measured/2,completePC:symbols.probe_complete/2}));
