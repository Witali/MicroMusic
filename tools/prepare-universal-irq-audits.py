from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/irq-release-audits';OUT.mkdir(parents=True,exist_ok=True)
source=ROOT/'tools/audit-universal-music.mjs'
text=source.read_text(encoding='utf-8')
def replace(old,new):
    global text
    assert text.count(old)==1,(old,text.count(old))
    text=text.replace(old,new)
replace("import {AVRCore} from '../web-player/lib/avr-core.js';", "import {AVRCore} from '../../web-player/lib/avr-core.js';\nimport {decodeAVR} from '../../web-player/lib/avr-transpiler.js';")
replace("import {UniversalReference} from './universal-reference.mjs';", "import {UniversalReference} from '../../tools/universal-reference.mjs';")
replace("const root=fileURLToPath(new URL('../',import.meta.url));", "const root=fileURLToPath(new URL('../../',import.meta.url));")
helper=r'''
const dfp=fs.readFileSync(path.join(root,'ATtiny88/Music/universal/vendor/ATtiny_DFP/3.4.278/include/avr/iotn88.h'),'utf8');
const registers=Object.fromEntries([...dfp.matchAll(/^#define (\w+) _SFR_(IO|MEM)8\((0x[\da-f]+)\)/gmi)]
 .map(([,name,space,value])=>[name,Number(value)+(space==='IO'?32:0)]));
const address=name=>{assert.ok(Number.isInteger(registers[name]),'Official DFP '+name);return registers[name];};
const bit=name=>{const m=dfp.match(new RegExp('^#define\\s+'+name+'\\s+(\\d+)\\s*$','m'));assert.ok(m);return 1<<Number(m[1]);};
const compareA=[address('OCR1AL'),address('OCR1AH')],comA=bit('COM1A0')|bit('COM1A1'),ddrA=bit('DDB1');
function byteHash(){
 const hash=createHash('sha256'),buffer=Buffer.allocUnsafe(65536);let at=0,count=0;
 return {byte(value){buffer[at++]=value;count++;if(at===buffer.length){hash.update(buffer);at=0;}},
  finish(){if(at)hash.update(buffer.subarray(0,at));return {sha256:hash.digest('hex'),bytes:count};}};
}
function writeDescriptors(core,bytes){
 const type=new Uint8Array(core.words),pointer=new Uint8Array(core.words),offset=new Int32Array(core.words);
 for(let pc=0;pc<bytes/2;pc++){
  const at=pc*2,i=decodeAVR(word(core.rom,at),word(core.rom,at+2));
  if(i.name==='STS'||i.name==='OUT'||i.name==='SBI'||i.name==='CBI'){
   type[pc]=1;offset[pc]=i.name==='STS'?i.k:32+(i.name==='OUT'?i.k:i.d);
   assert.equal(core.batch[pc],0,'Direct I/O writes use the observable single-step path');
  }else if(i.name==='ST'){
   type[pc]=2;pointer[pc]=i.s;offset[pc]=i.k<0?-1:i.k>=2?i.k-2:0;
   if(i.k!==1)assert.equal(core.batch[pc],0,'Non-postincrement stores use single-step');
  }
 }
 return {type,pointer,offset};
}
function attemptedWrite(core,stores){
 const pc=core.pc,kind=stores.type[pc];
 if(kind===1)return stores.offset[pc];
 if(kind===2){const s=stores.pointer[pc];return ((core.r[s]|core.r[s+1]<<8)+stores.offset[pc])&core.profile.pointerMask;}
 return -1;
}
export function traceSelfTest(){
 const ldi=(d,k)=>0xe000|((d-16)<<4)|(k&15)|((k&240)<<4);
 const words=[ldi(26,compareA[0]&255),ldi(27,compareA[0]>>8),ldi(16,0x5b),0x930d,0xcfff];
 const binary=Uint8Array.from(words.flatMap(w=>[w&255,w>>8]));
 const core=new AVRCore(binary,null,{target:'attiny88',fastIdle:false});
 core.data[compareA[0]]=0x5b;core.data[compareA[1]]=0x5a;core.timerTemp=0x5a;
 const stores=writeDescriptors(core,binary.length);
 assert.ok(core.runBlock());assert.equal(core.pc,3,'Batch stops before indirect I/O store');
 assert.equal(attemptedWrite(core,stores),compareA[0]);
 assert.equal(word(core.data,compareA[0]),0x5a5b);
 core.step();assert.equal(word(core.data,compareA[0]),0x5a5b,'Same-value store leaves data unchanged');
 return {nativeBlockExposesIndirectIO:true,sameValueWriteDetected:true,ocr1aDataAddresses:compareA};
}
'''
replace("export function audit(name,",helper+"\nexport function audit(name,")
replace(" const start=performance.now(),stopTicks=", " const stores=writeDescriptors(c,meta.engineBytes);\n const generatedActual=byteHash(),generatedReference=byteHash(),irqActual=byteHash(),irqReference=byteHash();\n let observableBoundaries=0,monoWriteAttempts=0;\n if(mono){assert.equal(c.profile.timer.ocra,compareA[0]);c.data[compareA[0]]=0x5b;c.data[compareA[1]]=0x5a;}\n const start=performance.now(),stopTicks=")
replace("   if(!c.inIRQ&&c.pc===tick){", "   if(mono){\n    observableBoundaries++;const attempted=attemptedWrite(c,stores);\n    if(compareA.includes(attempted)){monoWriteAttempts++;throw Error('Mono attempted OCR1A write at byte PC '+c.pc*2);}\n    assert.equal(word(c.data,compareA[0]),0x5a5b,'Mono preserves poisoned OCR1A during all execution');\n    assert.equal(c.data[address('DDRB')]&ddrA,0,'Mono never enables PB1');\n    assert.equal(c.data[address('TCCR1A')]&comA,0,'Mono never enables COM1A');\n   }\n   if(!c.inIRQ&&c.pc===tick){")
replace("      assert.equal(c.data[ring+pos],ref.ring[pos],", "      generatedActual.byte(c.data[ring+pos]);generatedReference.byte(ref.ring[pos]);\n      assert.equal(c.data[ring+pos],ref.ring[pos],")
replace("    checkedIRQOutputs++;", "    if(channels===2){irqActual.byte(c.data[c.profile.timer.ocra]);irqReference.byte(irqExpected[0]);}\n    irqActual.byte(c.data[c.profile.timer.ocrb]);irqReference.byte(irqExpected[channels===1?0:1]);\n    checkedIRQOutputs++;")
replace(" const passed=!failure;", " const generatedPwmActual=generatedActual.finish(),generatedPwmReference=generatedReference.finish();\n const consumedPwmActual=irqActual.finish(),consumedPwmReference=irqReference.finish();\n if(!failure&&(generatedPwmActual.sha256!==generatedPwmReference.sha256||consumedPwmActual.sha256!==consumedPwmReference.sha256))failure='PWM stream SHA mismatch';\n const passed=!failure;")
replace(" const report={variant:name,", " const report={generatedPwmActual,generatedPwmReference,consumedPwmActual,consumedPwmReference,\n  rawPwmStreamsEqual:passed,strictMonoOCR1ANoWrites:mono?passed&&monoWriteAttempts===0:null,\n  monoOCR1AWriteAttempts:mono?monoWriteAttempts:null,monoObservableBoundaries:mono?observableBoundaries:null,\n  monoPoisonedCompareA:mono?0x5a5b:null,monoPB1AndCOM1AInactive:mono?passed:null,\n  irqScratch:meta.irqScratch,irqScratchSelection:meta.irqScratchSelection,\n  reservedIORegisters:meta.reservedIORegisters,dfpRegisterSourceSha256:sha(dfp.replace(/\\r\\n/g,'\\n')),variant:name,")
replace("if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){", "if(process.argv.includes('--self-test')){console.log(JSON.stringify(traceSelfTest()));}\nelse if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){")
(OUT/'audit-with-write-trace.mjs').write_text(text,encoding='utf-8')
baseline=[]
for base,cpu in [('songs',8000000),('songs-micronucleus',16000000)]:
 for folder in sorted((ROOT/'ATtiny88/Music/universal'/base).iterdir()):
  if not (folder/'build-report.json').exists():continue
  meta=json.loads((folder/'build-report.json').read_text());score=json.loads((folder/'score.json').read_text())
  baseline.append(dict(base=base,name=folder.name,cpuHz=cpu,channels=score['channels'],controlTicks=score['controlTicks'],
   scoreSha256=hashlib.sha256(json.dumps(score,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),
   priorFlashSha256=meta['flashSha256']))
assert len(baseline)==18
if (OUT/'prepared.json').exists():
 previous=json.loads((OUT/'prepared.json').read_text())
 old={(row['base'],row['name']):row['scoreSha256']for row in previous['baseline']}
 assert {(row['base'],row['name']):row['scoreSha256']for row in baseline}==old,'ISR changes must preserve every source score'
manifest=dict(auditSourceSha256=hashlib.sha256(source.read_bytes()).hexdigest(),
 auditSourceTextLfSha256=hashlib.sha256(source.read_text(encoding='utf-8').encode()).hexdigest(),
 preparationSourceSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 instrumentedAuditSha256=hashlib.sha256((OUT/'audit-with-write-trace.mjs').read_bytes()).hexdigest(),baseline=baseline)
(OUT/'prepared.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('Prepared isolated full-song audit and baseline manifest; final audits have not started.')
