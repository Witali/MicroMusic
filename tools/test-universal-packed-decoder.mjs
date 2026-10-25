// Exercise the actual compiled C grammar routine, independently of musical
// scheduling. Build snapshots come from test-universal-stereo.mjs --engine-dir.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {AVRCore} from '../web-player/lib/avr-reference.js';
import {checkControlOrdering} from './universal-control-order-fixture.mjs';
const option=(name,fallback)=>process.argv.find(a=>a.startsWith('--'+name+'='))?.slice(name.length+3)||fallback;
const engineDirectory=option('engine-dir','build/backend-all-boards/8000000');
// A fast-layout build also retains the compact decoder. The optional second
// snapshot exercises both paths without requiring legacy code in USB images.
const fastEngineDirectory=option('fast-engine-dir','');
const reportFile=option('report','build/universal-packed-decoder-verification.json');
const common=spawnSync('git',['rev-parse','--git-common-dir'],{encoding:'utf8'});
assert.equal(common.status,0,common.stderr);
const checkout=path.dirname(path.resolve(common.stdout.trim()));
const bundled=path.join(checkout,'build/toolchains/python-3.13.3/python.exe');
const python=option('python',process.env.PYTHON||(fs.existsSync(bundled)?bundled:'python3'));
const fixtureSource=String.raw`
import importlib.util,json,random
s=importlib.util.spec_from_file_location('decoder_codec','tools/universal-music.py')
c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
out=[]
def save(name,packed,expected):
 assert c.unpack_grammar(packed)==expected
 out.append(dict(format=packed['format'],name=name,alphabet=list(packed['alphabet']),ruleData=list(packed['ruleData']),
  streamData=list(packed['streamData']),streamSymbols=len(packed['stream']),streamBytes=len(packed['streamData']),expected=expected))
for raw in [list(range(256)),[255]*31,[0],list(range(256))*3]:
 save('alphabet-'+str(len(raw)),c.pack_grammar(raw),raw)
rng=random.Random(0x554d3838)
raw=[rng.randrange(256)for _ in range(1024)]
save('random-byte-boundaries',c.pack_grammar(raw),raw)
# All 512 codes are legal. The last dictionary code 511 must not truncate.
alphabet=bytes(range(256));rules=[(i,255-i)for i in range(256)]
stream=list(range(512))
p=dict(format=9,alphabet=alphabet,rules=rules,stream=stream,
 ruleData=c._pack9(x for pair in rules for x in pair),streamData=c._pack9(stream))
save('code-511-and-256-terminals',p,list(range(256))+[v for pair in rules for v in pair])
# Balanced depth 12 reaches the maximum pending stack at actual command calls.
rules=[(0,1)]
for n in range(1,12):rules.append((2+n-1,2+n-1))
p=dict(format=9,alphabet=bytes([37,219]),rules=rules,stream=[13],
 ruleData=c._pack9(x for pair in rules for x in pair),streamData=c._pack9([13]))
save('maximum-depth-12',p,[37,219]*2048)
# A nine-bit rule index is also required when there is only one literal.
rules=[(0,0)]*511;stream=list(range(512))
p=dict(format=9,alphabet=bytes([219]),rules=rules,stream=stream,
 ruleData=c._pack9(x for pair in rules for x in pair),streamData=c._pack9(stream))
save('rule-index-510',p,[219]*1023)
for raw in [list(range(256)),[255]*31,[0],list(range(256))*3]:
 save('fast-alphabet-'+str(len(raw)),c.pack_fast_grammar(raw),raw)
rules=[(0,255)]
for n in range(1,12):rules.append((256+n-1,256+n-1))
p=dict(format=0,alphabet=b'',rules=rules,stream=[267],
 ruleData=bytes(v for pair in rules for sym in pair for v in (sym&255,sym>>8)),
 streamData=bytes([129,11]))
save('fast-maximum-depth-12',p,[0,255]*2048)
rules=[(i,255-i)for i in range(256)];stream=list(range(512));encoded=[]
for sym in stream:
 if sym<128:encoded.append(sym)
 else:encoded.extend([128|(sym>>8),sym&255])
p=dict(format=0,alphabet=b'',rules=rules,stream=stream,
 ruleData=bytes(v for pair in rules for sym in pair for v in (sym&255,sym>>8)),streamData=bytes(encoded))
save('fast-code-511-and-256-terminals',p,list(range(256))+[v for pair in rules for v in pair])
print(json.dumps(out))
`;
const generated=spawnSync(python,['-c',fixtureSource],{encoding:'utf8',maxBuffer:4*1024*1024});
assert.equal(generated.status,0,generated.stderr);
const fixtures=JSON.parse(generated.stdout),sha=b=>createHash('sha256').update(b).digest('hex');
const word=(data,a)=>data[a]|data[a+1]<<8;
const putWord=(data,a,value)=>{data[a]=value;data[a+1]=value>>8;};
const results=[],controlOrdering=[];
let cpuHz;
for(const [configuration,directory] of [['primary',engineDirectory],...(fastEngineDirectory?[['fast',fastEngineDirectory]]:[])]){
for(const backend of ['c','avr-asm']){
 const meta=JSON.parse(fs.readFileSync(path.join(directory,'engine-'+backend+'.json')));
 const engine=fs.readFileSync(path.join(directory,'engine-'+backend+'.bin'));
 assert.equal(sha(engine),meta.engineSha256,'Stable compiled engine snapshot');
 if(cpuHz===undefined)cpuHz=meta.cpuHz;
 assert.equal(meta.cpuHz,cpuHz,'All snapshots in one report use the same CPU clock');
 const supportsFast=Number.isInteger(meta.labels.packedSymbols);
 if(configuration==='fast')assert.ok(supportsFast,'--fast-engine-dir must retain the fast0 decoder');
 const at=name=>{assert.ok(Number.isInteger(meta.labels[name]),'Required symbol '+name);return meta.labels[name]-0x800000;};
 const state=at('um'),ruleAddress=at('ruleTable'),literalAddress=at('literalCount'),bitAddress=at('streamBit');
 for(const fixture of fixtures){
  if(fixture.format===0&&!supportsFast)continue;
  const payload=Uint8Array.from([...fixture.alphabet,...fixture.ruleData,...fixture.streamData]);
  const base=(engine.length+31)&~31,binary=new Uint8Array(base+payload.length);binary.set(engine);binary.set(payload,base);
  assert.ok(binary.length<=8192,'Boundary fixture fits the real device Flash');
  const core=new AVRCore(binary,null,{target:'attiny88',cpuHz:meta.cpuHz,fastIdle:false,fastBlocks:false});
  const rule=base+fixture.alphabet.length,stream=rule+fixture.ruleData.length;
  putWord(core.data,ruleAddress,rule);putWord(core.data,literalAddress,fixture.format===0?256:fixture.alphabet.length);
  putWord(core.data,state+184,stream);core.data[state+214]=0;core.data[bitAddress]=0;
  if(supportsFast)core.data[at('packedSymbols')]=fixture.format;
  // Depth 12 uses pending[0..11]; pending[12] is a reserved guard slot.
  core.data[state+210]=0xa6;core.data[state+211]=0x6a;
  // UMState stores ticks immediately after pending[13]; poison both bytes.
  core.data[state+212]=0x5a;core.data[state+213]=0xa5;
  let maxPending=0,maxCommandCycles=0;
  for(let index=0;index<fixture.expected.length;index++){
   core.pushPC(0);core.pc=meta.labels.command/2;const before=core.cyc;
   do{core.step();assert.ok(core.cyc-before<20000,'Bounded command expansion');
     maxPending=Math.max(maxPending,core.data[state+214]);
   }while(core.pc!==0);
   assert.equal(core.r[24],fixture.expected[index],backend+'/'+fixture.name+' byte '+index);
   assert.equal(core.r[1],0);assert.equal(core.sp,767);
   assert.equal(core.data[state+210],0xa6);assert.equal(core.data[state+211],0x6a);
   assert.equal(core.data[state+212],0x5a);assert.equal(core.data[state+213],0xa5);
   maxCommandCycles=Math.max(maxCommandCycles,core.cyc-before);
  }
  assert.ok(maxPending<=12);assert.equal(core.data[state+214],0);
  assert.equal(core.data[bitAddress],fixture.format===0?0:fixture.streamSymbols&7);
  assert.equal(word(core.data,state+184),stream+(fixture.format===0?fixture.streamBytes:Math.floor(fixture.streamSymbols*9/8)));
  assert.ok(core.minSP>=state+221,'Machine stack stays above the decoder state');
  if(fixture.name.includes('maximum-depth-12'))assert.equal(maxPending,12);
  results.push({backend,configuration,format:fixture.format,fixture:fixture.name,decodedBytes:fixture.expected.length,maxPending,maxCommandCycles,
   minSP:core.minSP,engineSha256:meta.engineSha256});
 }
 for(const mode of ['normal','raw-terminal','raw-interior'])
  controlOrdering.push(checkControlOrdering({meta,engine,python,backend,configuration,mode}));
}
}
const report={method:'Actual AVR C command() routines from isolated C/ASM engine builds; serialized fields generated in Python and checked byte for byte. Clock/IRQ admission is a separate full firmware audit.',
 cpuHz,
 sourceCodecSha256:sha(fs.readFileSync('tools/universal-music.py','utf8').replace(/\r\n/g,'\n')),
 sourceControlFixtureSha256:sha(fs.readFileSync('tools/universal-control-order-fixture.mjs','utf8').replace(/\r\n/g,'\n')),
 exactDecodedBytes:true,all512Codes:true,all256Terminals:true,maximumGrammarDepth:12,allStackSentinelsPreserved:true,
 formatsTested:[...new Set(results.map(row=>row.format))].sort((a,b)=>a-b),pendingGuardSlotPreserved:true,
 allControlOrderingMatches:true,controlModesTested:['normal','raw-terminal','raw-interior'],
 rawLevelOnlyCacheReuseChecked:true,rawContextDirtyRefreshChecked:true,controlOrdering,results};
fs.mkdirSync(path.dirname(reportFile),{recursive:true});fs.writeFileSync(reportFile,JSON.stringify(report,null,2)+'\n');
console.log(results.length+' compiled C/ASM decoder boundary cases: exact bytes, code 511, 256 terminals, depth 12, stack sentinels and stream positions; '+controlOrdering.length+' normal/raw control-order variants');
