// Full finite domain against independent BigInt and the original C scalar.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {CPU,avrInstruction} from 'avr8js';
const dir=resolve(process.argv[2]),binary=readFileSync(join(dir,'unit.bin'));
const meta=JSON.parse(readFileSync(join(dir,'input.json'),'utf8'));
assert.equal(typeof meta.compilerVersion,'string','Compiler identity is required');
assert.ok(meta.compilerVersion.trim().length>0,'Compiler identity must not be empty');
assert.equal(createHash('sha256').update(binary).digest('hex'),meta.binarySha256);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/)
 .map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const at=n=>{assert.ok(symbols.has(n),n);return symbols.get(n);};
const [value,result,command,status,end]=['pitch_value','pitch_result','pitch_command','pitch_status','__bss_end'].map(at);
const tables=[...symbols.keys()].filter(n=>n==='speex_nb1_pitch_root_table'||n.startsWith('speex_nb1_pitch_root_table.'));
assert.equal(tables.length,1);const table=at(tables[0]);assert.ok(table+128<32768);
const names=['pitch_original','pitch_lookup','pitch_threshold','pitch_selected'];
const entries=new Map(names.map((n,i)=>[at(n),i]));assert.equal(entries.size,4);
const sizes=new Map(readFileSync(join(dir,'sizes.txt'),'utf8').split(/\r?\n/)
 .map(l=>l.match(/^[0-9a-f]+\s+([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)]));
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048),saved=[...Array.from({length:16},(_,i)=>i+2),28,29];
let active=null,returns=0,minSP=2303;
const stats=names.map(name=>({name,bytes:sizes.get(name),calls:0,muls:0,lpm:0,minCycles:Infinity,maxCycles:0,totalCycles:0}));
function until(done){const limit=cpu.cycles+10000;while(!done()){
 assert.ok(cpu.cycles<limit,'Scalar timeout');const opcode=cpu.progMem[cpu.pc],entry=entries.get(cpu.pc*2);
 if(entry!==undefined){
  assert.equal(active,null);const original=saved.map(r=>cpu.data[r]),patterns=saved.map(r=>(returns*73+r*19)&255);
  saved.forEach((r,i)=>{cpu.data[r]=patterns[i];});active={entry,sp:cpu.SP,start:cpu.cycles,original,patterns,muls:0,flash:[]};
 }
 if(active){
  if((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300)++active.muls;
  if((opcode&0xfe0f)===0x9004||(opcode&0xfe0f)===0x9005||opcode===0x95c8)active.flash.push(cpu.dataView.getUint16(30,true));
 }
 avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end);
 if(active&&opcode===0x9508&&cpu.SP===active.sp+2){
  const a=active,s=stats[a.entry],cycles=cpu.cycles-a.start;
  assert.deepEqual(saved.map(r=>cpu.data[r]),a.patterns);assert.equal(cpu.data[1],0);
  const lookup=a.entry===1||(a.entry===3&&meta.tableEnabled);
  assert.deepEqual(a.flash,lookup?[table+cpu.data[value]-17]:[]);
  if(lookup)assert.equal(a.muls,0);
  ++s.calls;s.muls+=a.muls;s.lpm+=a.flash.length;s.totalCycles+=cycles;
  s.minCycles=Math.min(s.minCycles,cycles);s.maxCycles=Math.max(s.maxCycles,cycles);
  saved.forEach((r,i)=>{cpu.data[r]=a.original[i];});active=null;++returns;
 }
}}
// Mirrors every cast and arithmetic shift in the pinned polynomial, using
// arbitrary-precision integers independently of the target C implementation.
function root(p){
 let x=BigInt(2*p),k=0,t=x;while(t>=4n){t>>=2n;++k;}k-=6;
 x=k>0?x>>BigInt(2*k):x<<BigInt(-2*k);
 const word=x=>BigInt.asIntN(16,x),mul=(a,b)=>(word(a)*word(b))>>14n;
 const rt=word(3634n+mul(x,word(21173n+mul(x,word(-12627n+mul(x,4204n))))));
 return Number(rt>>BigInt(7-k));
}
until(()=>cpu.data[status]===1);const values=[];
for(let p=17;p<=144;p++){
 const expected=root(p);values.push(expected);assert.equal(binary[table+p-17],expected);
 for(let kind=1;kind<=4;kind++){
  cpu.data[value]=p;cpu.data[status]=1;cpu.data[command]=kind;until(()=>cpu.data[status]===2);
  assert.equal(cpu.dataView.getInt16(result,true),expected,`pitch ${p}, recipe ${kind}`);
  assert.equal(cpu.data[value],p);
 }
}
assert.equal(returns,128*4);
for(const s of stats)s.meanCycles=s.totalCycles/s.calls;
const report={scope:'Isolated scalar C arithmetic; no C decoder execution/timing',backend:meta.backend,
 compilerVersion:meta.compilerVersion,
 tableEnabled:meta.tableEnabled,binarySha256:meta.binarySha256,all128PitchCodes:true,values,
 originalThresholdTableAndSelectionExact:true,tableInFlash:true,exactFlashAddresses:true,
 lookupHasNoMuls:true,calleeSavedAndR1Returns:returns,arbitraryRegisterPatterns:true,
 statistics:stats,peakStack:2303-minSP,includesInterrupts:false,physicalBoardTested:false};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS',JSON.stringify(report));
if(process.argv.includes('--record')){
 const root=fileURLToPath(new URL('../',import.meta.url)),fixtures=[];
 for(const backend of ['asm','c'])for(const enabled of [true,false]){
  const folder=join(root,'build/nb1-pitch-unit',`${backend}-table${Number(enabled)}`);
  const input=JSON.parse(readFileSync(join(folder,'input.json'),'utf8'));
  const verified=JSON.parse(readFileSync(join(folder,'verification.json'),'utf8'));
  assert.equal(input.backend,backend);assert.equal(input.tableEnabled,enabled);
  assert.equal(typeof input.compilerVersion,'string','Compiler identity is required in every fixture');
  assert.ok(input.compilerVersion.trim().length>0,'Compiler identity must not be empty');
  assert.equal(verified.backend,backend);assert.equal(verified.tableEnabled,enabled);
  assert.equal(input.compilerVersion,verified.compilerVersion);
  assert.equal(input.binarySha256,verified.binarySha256);
  assert.equal(createHash('sha256').update(readFileSync(join(folder,'unit.bin'))).digest('hex'),input.binarySha256);
  assert.deepEqual(verified.values,values);assert.equal(verified.calleeSavedAndR1Returns,512);
  assert.ok(verified.originalThresholdTableAndSelectionExact&&verified.exactFlashAddresses&&verified.lookupHasNoMuls);
  fixtures.push({backend,tableEnabled:enabled,compilerVersion:input.compilerVersion,binarySha256:input.binarySha256,
   cases:128,checkedReturns:512,peakStackBytes:verified.peakStack,statistics:verified.statistics});
 }
 const sources=['src/nb1_pitch.h','src/avr_tables.h','src/speex_platform.h','src/avr_multiply.h','src/avr_fixed.h',
  'src/avr_shift.h','src/nb3_c_math.h','tests/build_nb1_pitch.py','tests/avr_nb1_pitch.c','tests/verify_nb1_pitch.mjs',
  'tools/build.py','tools/apply_profile.py','handoff/upstream/tools/apply_upstream_port.py',
  'handoff/upstream/tools/apply_tight_exc.py','vendor/speex-1.2.1/libspeex/math_approx.h',
  'vendor/speex-1.2.1/libspeex/fixed_generic.h','vendor/speex-1.2.1/libspeex/arch.h'];
 const sourceSha256=Object.fromEntries(sources.map(n=>[n,createHash('sha256')
  .update(readFileSync(join(root,n),'utf8').replace(/\r\n/g,'\n')).digest('hex')]));
 const receipt={scope:'Isolated exact NB1 pitch-root recipe screen; no complete decoder or IRQ timing claim',
  target:'ATmega328P / AVR5 / GNU ABI',compilerOptions:'-std=c11 -fwrapv -fno-strict-aliasing -mmcu=atmega328p -Os -flto -fno-ipa-icf -mcall-prologues -mrelax -ffunction-sections -fdata-sections; O2 wrappers',
  simulator:'avr8js 0.21.1',sourceHashMode:'UTF-8 text normalized to LF',sourceSha256,
  pitchMin:17,pitchMax:144,tableBytes:128,values,fixtures,
  portableArithmeticExplicitlySelectable:true,allRecipesExact:true,calleeSavedAndR1Exact:true,
  includesInterrupts:false,physicalBoardTested:false,cDecoderExecuted:false,
  limits:['Only the finite private pitch domain 17..144 is supported by lookup and threshold recipes.',
   'Measured cycles include function RET, exclude caller overhead and interrupts.',
   'No whole-frame, continuous playback, SPI transport or physical-board claim is made.']};
 writeFileSync(join(root,'reports/nb1-pitch-unit.json'),JSON.stringify(receipt,null,2)+'\n');
 console.log('Recorded four source-bound pitch-root fixtures');
}
