// Prepare an ELF/DWARF2 control and project-local read-only Studio hooks.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {resolve,join,dirname,relative,parse,isAbsolute} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {oracleSuite} from './lib/attiny13a-oracle-cases.mjs';
import {AT13_MEMORY as MEMORY} from '../lib/attiny13a-registers.js';
const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{'out-dir':{type:'string',default:'build/probes/attiny13a-studio'},
  'avr-bin':{type:'string'},nonce:{type:'string',default:'studio-control-v1'},suite:{type:'string',default:'core'},
  'breakpoint-address-unit':{type:'string',default:'unconfirmed'}}});
assert.match(values.nonce,/^[A-Za-z0-9_-]{1,64}$/);
const {cases:probeCases,forms:caseForms}=oracleSuite(values.suite);
const addressUnit=values['breakpoint-address-unit'];assert.ok(['unconfirmed','bytes','words'].includes(addressUnit));
const out=resolve(root,values['out-dir']),rel=relative(resolve(root,'build'),out);
assert.ok(rel&&!rel.startsWith('..')&&!isAbsolute(rel),'Keep generated oracle files in build/');
mkdirSync(out,{recursive:true});const suffix=process.platform==='win32'?'.exe':'';
let bin=values['avr-bin'];
for(let p=root;!bin;p=dirname(p)){
  const candidate=join(p,'build/toolchains/avr-7.3.0/bin');
  if(existsSync(join(candidate,'avr-gcc'+suffix)))bin=candidate;
  if(p===parse(p).root)break;
}
assert.ok(bin,'Pass --avr-bin for the registered AVR toolchain');
const run=(tool,args)=>{const r=spawnSync(join(bin,tool+suffix),args,{cwd:root,encoding:'utf8'});
  if(r.error)throw r.error;assert.equal(r.status,0,r.stderr||r.stdout);return r.stdout;};
const read=p=>readFileSync(resolve(root,p)),text=p=>read(p).toString().replaceAll('\r\n','\n');
const sha=b=>createHash('sha256').update(b).digest('hex');
const folder='web-player/native/devices/attiny13a',vendor='web-player/vendor/microchip/ATtiny_DFP/3.4.278';
const header=vendor+'/include/avr/iotn13a.h',provenance=JSON.parse(text(vendor+'/provenance.json'));
assert.equal(sha(read(header)),provenance.files['include/avr/iotn13a.h'].sha256);
const sourcePaths=[folder+'/core-oracle.S',folder+'/core-oracle.c',folder+'/oracle-debughooks.py',
  'web-player/native/attiny13a-registers.generated.inc','web-player/scripts/lib/avr-core-probe-cases.mjs',
  'web-player/scripts/lib/attiny13a-oracle-cases.mjs',
  'web-player/scripts/build-attiny13a-oracle.mjs','web-player/lib/attiny13a-registers.js',vendor+'/provenance.json',header];
const sources=Object.fromEntries(sourcePaths.map(p=>[p,sha(text(p))]));
const compilerVersion=run('avr-gcc',['--version']).split(/\r?\n/)[0];
assert.equal(probeCases.length,12,'Review the 60-byte record/stack before extending this control');
const buildId=Array.from(Buffer.from(sha(JSON.stringify({sources,compilerVersion,nonce:values.nonce,addressUnit,suite:values.suite})).slice(0,8),'hex'));
const stores=offset=>['sts oracle_record+'+offset+',r16','sts oracle_record+'+(offset+1)+',r19',
  'sts oracle_record+'+(offset+2)+',r8','sts oracle_record+'+(offset+3)+',r9'];
function sequence(name,c,offset){
  return [name+':',`ldi r16,${c.a}`,`ldi r17,${c.b}`,c.setup||'',`ldi r18,${c.flags}`,
    'out SREG,r18','in r8,TCNT0',name+'_target:',(c.asm||'').replaceAll('probe_packet','oracle_record'),
    name+'_after:','in r19,SREG','in r9,TCNT0',...stores(offset)].filter(Boolean).join('\n')+'\n';
}
let generated=sequence('oracle_control',{a:0,b:0,flags:0},8);
probeCases.forEach((c,n)=>generated+=sequence('oracle_case_'+n,c,12+n*4));
for(const [n,b]of buildId.entries())generated+=`ldi r16,${b}\nsts oracle_record+${4+n},r16\n`;
for(const n of [3,2,1,0])generated+=`ldi r16,${[65,86,49,51][n]}\nsts oracle_record+${n},r16\n`;
writeFileSync(join(out,'oracle-cases.generated.inc'),generated);
let hooks=text(folder+'/oracle-debughooks.py');
for(const [anchor,value]of [['BUILD_ID = None','BUILD_ID = ('+buildId.join(', ')+')'],
  ['CASE_COUNT = None','CASE_COUNT = '+probeCases.length]]){
  assert.equal(hooks.split(anchor).length,2);hooks=hooks.replace(anchor,value);
}
const elf=join(out,'oracle.elf'),binaryPath=join(out,'oracle.bin');
const flags=['-mmcu=attiny13a','-Os','-std=gnu11','-Wall','-Wextra','-Werror','-gdwarf-2',
  '-nostartfiles','-nostdlib','-DORACLE_CASE_COUNT='+probeCases.length,'-I'+vendor+'/include',
  '-I'+out,'-fdebug-prefix-map='+root.replaceAll('\\','/').replace(/\/$/,'')+'=.',
  '-Wl,-Map='+join(out,'oracle.map')];
run('avr-gcc',[...flags,folder+'/core-oracle.S',folder+'/core-oracle.c','-o',elf]);
run('avr-objcopy',['-O','binary','-R','.eeprom',elf,binaryPath]);
const binary=readFileSync(binaryPath);assert.ok(binary.length<=MEMORY.FLASHEND+1);
const nm=run('avr-nm',['-n',elf]);
const symbols=Object.fromEntries(nm.split(/\r?\n/).map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(\S+)$/i)).filter(Boolean)
  .map(m=>[m[2],parseInt(m[1],16)]));
assert.ok(Number.isInteger(symbols.oracle_complete));
const recordAddress=symbols.oracle_record-0x800000,recordBytes=12+probeCases.length*4;
assert.equal(recordAddress,MEMORY.RAMSTART);assert.ok(recordAddress+recordBytes<=MEMORY.RAMEND-3);
const dwarf=run('avr-objdump',['--dwarf=info',elf]);
const dwarfVersions=[...dwarf.matchAll(/Version:\s+(\d+)/g)].map(m=>Number(m[1]));
assert.ok(dwarfVersions.length&&dwarfVersions.every(v=>v===2),'Studio requires DWARF2');
assert.ok(dwarf.includes('oracle_record'),'Typed global must be present in debug info');
for(const [anchor,value]of [['COMPLETE_BYTE_ADDRESS = None','COMPLETE_BYTE_ADDRESS = '+symbols.oracle_complete],
  ['BREAKPOINT_ADDRESS_UNIT = "unconfirmed"','BREAKPOINT_ADDRESS_UNIT = '+JSON.stringify(addressUnit)]]){
  assert.equal(hooks.split(anchor).length,2);hooks=hooks.replace(anchor,value);
}
writeFileSync(join(out,'debughooks.py'),hooks);
const catalogPath='web-player/reports/attiny13a-instructions.json',catalog=JSON.parse(text(catalogPath));
const primaryForms=[...new Set(caseForms)];
for(const c of probeCases)if(c.form)assert.equal(c.manualSection,catalog.instructions.find(i=>i.form===c.form)?.manualSection);
const descriptor={schema:'micromusic-attiny13a-studio-control-v1',device:'ATtiny13A',
  officialSessionExecuted:false,hardwareTested:false,buildId,nonce:values.nonce,suite:values.suite,cases:probeCases,
  recordAddress,recordBytes,recordLayout:'AV13/build4/empty-control4/cases(result,SREG,TCNT-before,TCNT-after)',
  flashBytes:binary.length,flashSha256:sha(binary),elfSha256:sha(readFileSync(elf)),
  debughooksSha256:sha(Buffer.from(hooks)),compilerVersion,dwarfVersions,sources,
  flags:flags.map(s=>s.replaceAll('\\','/').replaceAll(out.replaceAll('\\','/'),'<out>')
    .replaceAll(root.replaceAll('\\','/').replace(/\/$/,''),'<repo>')),
  breakpointAddressUnit:addressUnit,debuggerApiBindingVerified:false,
  executionContract:{externalProgramming:false,interrupts:'disabled throughout',watchdogAlwaysOnFuse:'unprogrammed',
    timer0Clock:'clkIO/1',minimumStackBytes:4,calibration:'empty-stimulus counter delta; no oscillator measurement'},
  stopSymbol:'oracle_complete',stopByteAddress:symbols.oracle_complete,
  caseSpans:probeCases.map((c,n)=>({id:c.id,primaryForm:caseForms[n],targetByteAddress:symbols['oracle_case_'+n+'_target'],
    afterByteAddress:symbols['oracle_case_'+n+'_after'],sequenceCycles:c.cycles})),
  coverage:{sourceSha256:sha(text(catalogPath)),totalForms:catalog.instructions.length,
    preparedPrimaryForms:primaryForms.length,forms:catalog.instructions.map(i=>({form:i.form,
      preparation:primaryForms.includes(i.form)?'primary-stimulus-prepared':'not-yet-targeted',officialObserved:false}))},
  vendor:{package:provenance.package,version:provenance.version,sourceUrl:provenance.sourceUrl,headerSha256:sha(read(header))}};
writeFileSync(join(out,'descriptor.json'),JSON.stringify(descriptor,null,2)+'\n');
console.log(JSON.stringify({flashBytes:binary.length,recordBytes,stackBytes:MEMORY.RAMEND-recordAddress-recordBytes+1,
  cases:probeCases.length,suite:values.suite,dwarfVersions,stopByteAddress:symbols.oracle_complete,officialSessionExecuted:false}));
