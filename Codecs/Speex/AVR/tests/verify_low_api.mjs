// Variable-size calls, all enabled modes, error guards, padding and reset.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {CPU,avrInstruction} from 'avr8js';
const dir=resolve(process.argv[2]),input=resolve(process.argv[3]);
const meta=JSON.parse(readFileSync(join(dir,'backend.json'))),data=JSON.parse(readFileSync(join(input,'input.json')));
const binary=readFileSync(join(dir,'api.bin')),raw=readFileSync(join(input,'packets32.bin')),expected=readFileSync(join(input,'oracle.pcm'));
const hash=b=>createHash('sha256').update(b).digest('hex');
assert.equal(hash(binary),meta.binarySha256);assert.equal(hash(raw),data.inputSha256);assert.equal(hash(expected),data.pcmSha256);
assert.equal(meta.wideband,data.wideband);assert.equal(raw.length,data.frames*32);
const size=meta.wideband?640:320;assert.equal(expected.length,data.frames*size);
const symbols=new Map(readFileSync(join(dir,'symbols.txt'),'utf8').split(/\r?\n/).map(l=>l.match(/^([0-9a-f]+)\s+\w\s+(.+)$/)).filter(Boolean).map(m=>[m[2],parseInt(m[1],16)&65535]));
const address=name=>{assert.ok(symbols.has(name),name);return symbols.get(name);};
const [packet,bytes,flags,command,status,result,pcm,end]=['low_api_packet','low_api_bytes','low_api_flags','low_api_command','low_api_status','low_api_result','low_api_pcm','__bss_end'].map(address);
const chunks=meta.wideband?address('low_api_chunks'):-1;
const program=new Uint16Array(16384).fill(65535);new Uint8Array(program.buffer).set(binary);
const cpu=new CPU(program,2048);let output=[],lastChunk=0,minSP=2303,rejected=0;
const countMean=process.argv.includes('--count-mean'),meanEntry=countMean?address('speex_low_mean_avr'):-1;
let meanActive=null,meanCalls=0,meanMultiplies=0;
const countValues=process.argv.includes('--count-noise-values');
const valuesNames=[...symbols.keys()].filter(n=>n==='speex_low_noise_values5'||n.startsWith('speex_low_noise_values5.'));
if(countValues)assert.equal(valuesNames.length,1,'Noise preparation entry');
const valuesEntry=countValues?address(valuesNames[0]):-1;
let valuesActive=null,valuesCalls=0,valuesMultiplies=0;
const countFold=process.argv.includes('--count-noise-fold');
const foldEntry=countFold?address('speex_wb_noise_fold40_avr'):-1;
let foldActive=null,foldCalls=0,foldMultiplies=0;
const countVocoder=process.argv.includes('--count-vocoder');
const zeroVocoderAvailable=symbols.has('speex_nb1_synthesize40_zero_avr');
const vocoderEntries=new Map();
if(countVocoder){
 vocoderEntries.set(address('speex_nb1_synthesize40_avr'),'general');
 if(zeroVocoderAvailable)vocoderEntries.set(address('speex_nb1_synthesize40_zero_avr'),'zero');
}
const olGains=countVocoder?readFileSync(fileURLToPath(new URL('../vendor/speex-1.2.1/libspeex/nb_celp.c',import.meta.url)),'utf8')
 .match(/ol_gain_table\[32\]=\{([^}]+)\}/)[1].split(',').map(Number):[];
let expectedZeroContext=false;
const vocoderPaths={general:{calls:0,muls:0},zero:{calls:0,muls:0}};
let vocoderActive=null,vocoderCalls=0,vocoderMultiplies=0;
const countNb1Gain=process.argv.includes('--count-nb1-gain');
const countPrepare=process.argv.includes('--count-noise-prepare')||countNb1Gain;
const gainTables=[...symbols.keys()].filter(n=>n==='speex_nb1_gain_table'||n.startsWith('speex_nb1_gain_table.'));
if(countNb1Gain)assert.equal(gainTables.length,1,'Exactly one finite NB1 gain table');
const nb1GainTable=countNb1Gain?address(gainTables[0]):-1;
let gainLookups=0,expectedGainCode=0;const gainHistogram=Array(16).fill(0);
if(countNb1Gain)for(let code=0;code<16;code++){
 const c=(2185n*BigInt(code<<6)+16384n)>>15n,g=Number((24576n*(c-13n)+8192n)>>14n);
 assert.equal(binary[nb1GainTable+code],Math.max(0,Math.min(64,g)));
}
const prepareNames=[...symbols.keys()].filter(n=>n==='speex_nb1_excitation_prepare'||n.startsWith('speex_nb1_excitation_prepare.'));
if(countPrepare)assert.equal(prepareNames.length,1,'NB1 frame preparation entry');
const prepareEntry=countPrepare?address(prepareNames[0]):-1;
let prepareActive=null,prepareCalls=0,prepareMultiplies=0;const prepareCounts=[];
const prepareGroups={zero:{calls:0,muls:0,min:Infinity,max:0},nonzero:{calls:0,muls:0,min:Infinity,max:0}};
const countLowFusion=process.argv.includes('--count-low-fusion'),lowEntries=new Map();
const lowStats={2:{calls:0,muls:0},8:{calls:0,muls:0}};let lowActive=null;
if(countLowFusion)for(const m of [2,8]){
 const name=`speex_wb_excitation_nb${m}_40_avr`;
 if(meta.wideband)assert.ok(symbols.has(name),name);
 if(symbols.has(name))lowEntries.set(address(name),m);
}
const countForcedZero=process.argv.includes('--count-forced-zero');
const zeroNames=[...symbols.keys()].filter(n=>n==='speex_nb8_zero_frame'||n.startsWith('speex_nb8_zero_frame.'));
if(countForcedZero)assert.equal(zeroNames.length,1,'NB8 zero-frame producer');
const zeroFrameEntry=countForcedZero?address(zeroNames[0]):-1;
const zeroVectorEntry=countForcedZero?address('speex_avr_zero_innovation_n'):-1;
const countForcedOne=process.argv.includes('--count-forced-one');
const oneEntry=countForcedOne?address('speex_avr_forced_innovation_n'):-1;
const adaptiveEntry=countForcedZero||countForcedOne?address('speex_avr_long_innovation_n'):-1;
let oneActive=null,oneCalls=0,oneSamples=0,oneMuls=0,oneFrames=0,adaptiveCalls=0,expectedCoefficient=0;
const oneCounts=Array(11).fill(0);
const countForcedQ6=process.argv.includes('--count-forced-q6');
let q6Start=-1,q6Active=null,q6Calls=0,q6Muls=0,q6Cycles=0;
if(countForcedQ6){
 const frames=[...symbols.keys()].filter(n=>n==='speex_nb8_excitation_frame'||n.startsWith('speex_nb8_excitation_frame.'));
 assert.equal(frames.length,1);const start=address(frames[0]);
 const stop=Math.min(...[...symbols.values()].filter(a=>a>start&&a<binary.length));
 const pattern=[[0xff88,0x0300],[0xff00,0x0100],[0xfc00,0x9c00],[0xfc00,0x2c00],[0xfc00,0x0c00],
  [0xffff,0x2411],[0xfc00,0x1c00],[0xf000,0x5000],[0xf000,0x4000],[0xf000,0x4000],
  [0xfc00,0x0c00],[0xfc00,0x1c00],[0xfc00,0x1c00],[0xfc00,0x0c00],[0xfc00,0x1c00],[0xfc00,0x1c00]];
 const matches=[];
 for(let p=start/2;p+pattern.length<=stop/2;p++)if(pattern.every(([mask,value],i)=>(program[p+i]&mask)===value))matches.push(p*2);
 assert.equal(matches.length,1,'One exact inline Q6 body in the real controller');q6Start=matches[0];
}
let zeroActive=null,zeroFrameCalls=0,zeroVectorCalls=0,zeroFrameMuls=0,zeroMinMuls=Infinity,zeroMaxMuls=0;
const previousRead=cpu.readData.bind(cpu);
cpu.readData=a=>{if(zeroActive)zeroActive.reads.add(a);return previousRead(a);};
function until(predicate){const deadline=cpu.cycles+3000000;while(!predicate()){
 assert.ok(cpu.cycles<deadline,'API timeout');const opcode=cpu.progMem[cpu.pc];
 if(cpu.pc*2===meanEntry){
  assert.equal(meanActive,null);const a=cpu.dataView.getInt16(24,true),b=cpu.dataView.getInt16(22,true);
  meanActive={sp:cpu.SP,muls:0,expected:Number((26214n*BigInt(a)+6554n*BigInt(b)+16384n)>>15n)};
 }
 if(meanActive&&((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300))++meanActive.muls;
 if(cpu.pc*2===valuesEntry){assert.equal(valuesActive,null);valuesActive={sp:cpu.SP,muls:0};}
 if(valuesActive&&((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300))++valuesActive.muls;
 if(cpu.pc*2===foldEntry){assert.equal(foldActive,null);foldActive={sp:cpu.SP,muls:0};}
 if(foldActive&&((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300))++foldActive.muls;
 if(vocoderEntries.has(cpu.pc*2)){
  assert.equal(vocoderActive,null);const path=vocoderEntries.get(cpu.pc*2);
  assert.equal(path,zeroVocoderAvailable&&expectedZeroContext?'zero':'general','Prepared-context vector selection');
  vocoderActive={sp:cpu.SP,muls:0,path};
 }
 if(vocoderActive&&((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300))++vocoderActive.muls;
 if(cpu.pc*2===prepareEntry){assert.equal(prepareActive,null);prepareActive={sp:cpu.SP,muls:0,gainReads:[],zeroGain:expectedGainCode<4};}
 if(prepareActive&&((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300))++prepareActive.muls;
 if(prepareActive&&countNb1Gain&&((opcode&0xfe0f)===0x9004||(opcode&0xfe0f)===0x9005||opcode===0x95c8)){
  const a=cpu.dataView.getUint16(30,true);if(a>=nb1GainTable&&a<nb1GainTable+16)prepareActive.gainReads.push(a);
 }
 if(lowEntries.has(cpu.pc*2)){assert.equal(lowActive,null);lowActive={mode:lowEntries.get(cpu.pc*2),sp:cpu.SP,muls:0};}
 if(lowActive&&((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300))++lowActive.muls;
 if(cpu.pc*2===zeroFrameEntry){assert.equal(zeroActive,null);zeroActive={sp:cpu.SP,blocks:[],reads:new Set(),muls:0};}
 if(zeroActive){
  assert.notEqual(cpu.pc*2,adaptiveEntry,'No adaptive kernel in a zero-coefficient frame');
  assert.notEqual(cpu.pc*2,oneEntry,'No one-tap adaptive kernel in a zero-coefficient frame');
  if((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300)++zeroActive.muls;
 }
 if(cpu.pc*2===zeroVectorEntry&&cpu.data[16]===20){
  assert.ok(zeroActive,'Twenty-word zero rows belong to the zero-frame producer');
  zeroActive.blocks.push(cpu.dataView.getUint16(24,true));++zeroVectorCalls;
 }
 if(cpu.pc*2===adaptiveEntry)++adaptiveCalls;
 if(cpu.pc*2===oneEntry){
  assert.equal(oneActive,null);assert.equal(cpu.data[14],expectedCoefficient);
  const n=cpu.data[12];assert.ok(n>=1&&n<=10);oneActive={sp:cpu.SP,n,muls:0};
 }
 if(oneActive&&((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300))++oneActive.muls;
 if(cpu.pc*2===q6Start){
  assert.equal(q6Active,null);
  const hi=16+((opcode>>4)&7),coefficientReg=16+(opcode&7),mul=program[cpu.pc+2],lo=(mul>>4)&31;
  assert.equal(hi,lo+1);assert.equal((mul&15)|((mul>>5)&16),coefficientReg);
  const value=cpu.dataView.getInt16(lo,true),coefficient=cpu.data[coefficientReg];assert.equal(coefficient,expectedCoefficient);
  const target=2*((program[cpu.pc+1]>>4)&15);
  q6Active={start:cpu.cycles,target,lo,hi,coefficientReg,value,coefficient,
   expected:Number((BigInt(value)*(BigInt(coefficient)<<7n)+4096n)>>13n),muls:0};
 }
 if(q6Active&&((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300))++q6Active.muls;
 avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'SRAM collision');
 if(q6Active&&cpu.pc*2===q6Start+32){
  const a=q6Active,cycles=cpu.cycles-a.start;assert.equal(cycles,18);assert.equal(a.muls,2);
  assert.equal(cpu.dataView.getInt16(a.target,true),a.expected);assert.equal(cpu.data[1],0);
  assert.equal(cpu.dataView.getInt16(a.lo,true),a.value);assert.equal(cpu.data[a.coefficientReg],a.coefficient);
  ++q6Calls;q6Muls+=a.muls;q6Cycles+=cycles;q6Active=null;
 }
 if(oneActive&&opcode===0x9508&&cpu.SP===oneActive.sp+2){
  assert.equal(oneActive.muls,6*oneActive.n);assert.equal(cpu.data[1],0);
  ++oneCalls;++oneCounts[oneActive.n];oneSamples+=oneActive.n;oneMuls+=oneActive.muls;oneActive=null;
 }
 if(meanActive&&opcode===0x9508&&cpu.SP===meanActive.sp+2){
  assert.equal(cpu.dataView.getInt16(24,true),meanActive.expected,'Mean in real mixed decoder');
  assert.equal(meanActive.muls,4);assert.equal(cpu.data[1],0);
  ++meanCalls;meanMultiplies+=meanActive.muls;meanActive=null;
 }
 if(valuesActive&&opcode===0x9508&&cpu.SP===valuesActive.sp+2){
  assert.equal(valuesActive.muls,0,'No products in noise values');assert.equal(cpu.data[1],0);
  ++valuesCalls;valuesMultiplies+=valuesActive.muls;valuesActive=null;
 }
 if(foldActive&&opcode===0x9508&&cpu.SP===foldActive.sp+2){
  assert.equal(foldActive.muls,29,'Four second-stage transforms plus subframe address');assert.equal(cpu.data[1],0);
  ++foldCalls;foldMultiplies+=foldActive.muls;foldActive=null;
 }
 if(vocoderActive&&opcode===0x9508&&cpu.SP===vocoderActive.sp+2){
  assert.equal(vocoderActive.muls,160,'Forty exact single-product mean updates');assert.equal(cpu.data[1],0);
  ++vocoderCalls;vocoderMultiplies+=vocoderActive.muls;
  ++vocoderPaths[vocoderActive.path].calls;vocoderPaths[vocoderActive.path].muls+=vocoderActive.muls;vocoderActive=null;
 }
 if(prepareActive&&opcode===0x9508&&cpu.SP===prepareActive.sp+2){
  if(countNb1Gain){assert.deepEqual(prepareActive.gainReads,[nb1GainTable+expectedGainCode]);++gainLookups;++gainHistogram[expectedGainCode];}
  assert.equal(cpu.data[1],0);++prepareCalls;prepareMultiplies+=prepareActive.muls;prepareCounts.push(prepareActive.muls);
  const group=prepareGroups[prepareActive.zeroGain?'zero':'nonzero'];++group.calls;group.muls+=prepareActive.muls;group.min=Math.min(group.min,prepareActive.muls);group.max=Math.max(group.max,prepareActive.muls);
  prepareActive=null;
 }
 if(lowActive&&opcode===0x9508&&cpu.SP===lowActive.sp+2){
  assert.equal(lowActive.muls,lowActive.mode===2?604:602);assert.equal(cpu.data[1],0);
  ++lowStats[lowActive.mode].calls;lowStats[lowActive.mode].muls+=lowActive.muls;lowActive=null;
 }
 if(zeroActive&&opcode===0x9508&&cpu.SP===zeroActive.sp+2){
  const first=zeroActive.blocks[0];assert.equal(zeroActive.blocks.length,8);
  assert.deepEqual(zeroActive.blocks,Array.from({length:8},(_,i)=>first+40*i),'Eight complete contiguous rows');
  for(const a of zeroActive.reads)assert.ok(a<first-290||a>=first+320,'No excitation-history/output reads');
  assert.equal(cpu.data[1],0);++zeroFrameCalls;zeroFrameMuls+=zeroActive.muls;
  zeroMinMuls=Math.min(zeroMinMuls,zeroActive.muls);zeroMaxMuls=Math.max(zeroMaxMuls,zeroActive.muls);zeroActive=null;
 }
 if(meta.wideband&&cpu.data[chunks]!==lastChunk){lastChunk=cpu.data[chunks];const at=cpu.dataView.getUint16(pcm,true);output.push(Buffer.from(cpu.data.subarray(at,at+160)));}
}}
until(()=>cpu.data[status]===1);
function decode(payload,width,invalidFlags=0){
 const callsBefore=meanCalls,valuesBefore=valuesCalls,foldBefore=foldCalls,vocoderBefore=vocoderCalls,prepareBefore=prepareCalls;
 const lowBefore={2:lowStats[2].calls,8:lowStats[8].calls};
 const zeroBefore=zeroFrameCalls,vectorsBefore=zeroVectorCalls;
 const oneBefore=oneSamples,oneMulsBefore=oneMuls,adaptiveBefore=adaptiveCalls;
 const q6Before=q6Calls;
 const gainBefore=gainLookups;expectedGainCode=((payload[3]&3)<<2)|(payload[4]>>6);
 expectedZeroContext=expectedGainCode<4||Math.floor(28406*olGains[(payload[4]>>1)&31]/32768)<=4096;
 expectedCoefficient=Math.min(63,(2185*((((payload[3]&3)<<2)|(payload[4]>>6))<<6)+16384)>>15);
 cpu.data.set(payload,packet);cpu.data[bytes]=width;cpu.data[flags]=invalidFlags;
 output=[];cpu.data[status]=1;cpu.data[command]=1;until(()=>cpu.data[status]===2);
 assert.ok(Buffer.from(cpu.data.subarray(packet,packet+32)).equals(payload),'Read-only packet');
 const code=cpu.dataView.getInt8(result);
 if(countMean)assert.equal(meanCalls-callsBefore,code===0&&(payload[0]>>3)===1?160:0,'Mean only in valid NB1 frames');
 if(countValues)assert.equal(valuesCalls-valuesBefore,code===0&&(payload[0]>>3)===1?1:0,'Noise table once per valid NB1 frame');
 if(countFold)assert.equal(foldCalls-foldBefore,code===0&&(payload[0]>>3)===1?4:0,'Fold table four times per valid NB1 frame');
 if(countVocoder)assert.equal(vocoderCalls-vocoderBefore,code===0&&(payload[0]>>3)===1?4:0,'Four vocoder quarters only in valid NB1 frames');
 if(countPrepare)assert.equal(prepareCalls-prepareBefore,code===0&&(payload[0]>>3)===1?1:0,'Prepare only valid NB1 frames');
 if(countLowFusion)for(const m of [2,8])assert.equal(lowStats[m].calls-lowBefore[m],
  meta.wideband&&code===0&&(payload[0]>>3)===m?4:0,'Fused high-band only for matching valid WB mode');
 if(countForcedZero){
  const eligible=code===0&&(payload[0]>>3)===8&&(((payload[3]&3)<<2)|(payload[4]>>6))===0;
  assert.equal(zeroFrameCalls-zeroBefore,eligible?1:0,'Fast path only for valid coefficient0 NB8/WB5.75');
  assert.equal(zeroVectorCalls-vectorsBefore,eligible?8:0,'Eight twenty-sample zero-adaptive rows');
 }
 if(countForcedOne){
  const eligible=code===0&&(payload[0]>>3)===8&&expectedCoefficient!==0;
  assert.equal(oneSamples-oneBefore,eligible?160:0,'One-tap samples only for valid nonzero-coefficient NB8');
  assert.equal(oneMuls-oneMulsBefore,eligible?960:0,'Six MULs per one-tap sample');
  if((payload[0]>>3)===8)assert.equal(adaptiveCalls,adaptiveBefore,'No three-tap kernel for NB8');
  if(eligible)++oneFrames;
 }
 if(countForcedQ6){
  const eligible=code===0&&(payload[0]>>3)===8&&expectedCoefficient!==0;
  const pitch=17+((payload[2]&1)<<6)+(payload[3]>>2);
  const expected=eligible?4*Array.from({length:40},(_,j)=>Math.floor(j/pitch)).reduce((a,b)=>a+b,0):0;
  assert.equal(q6Calls-q6Before,expected,'Exact short-lag ancestor count; no calls in rejected/other/zero frames');
 }
 if(countNb1Gain)assert.equal(gainLookups-gainBefore,code===0&&(payload[0]>>3)===1?1:0,'Gain read once only for a valid NB1 frame');
 return {code,pcm:meta.wideband?Buffer.concat(output):Buffer.from(cpu.data.subarray(pcm,pcm+320)),callbacks:output.length};
}
function reject(payload,width,badFlags=0){const answer=decode(payload,width,badFlags);assert.equal(answer.code,-1);assert.equal(answer.callbacks,0);rejected++;}
for(let f=0;f<data.frames;f++){
 const payload=Buffer.from(raw.subarray(f*32,(f+1)*32)),width=data.packetLengths[f];
 reject(payload,0);reject(payload,width-1);reject(payload,width+1);reject(payload,width,1);reject(payload,width,2);
 const bad=Buffer.from(payload);bad[0]|=248;reject(bad,width);
 if(meta.wideband){const broken=Buffer.from(payload),bit=data.meaningfulBits[f]-36;broken[bit>>3]^=1<<(7-(bit&7));reject(broken,width);}
 if(f&1){const padding=width*8-data.meaningfulBits[f];if(padding)payload[width-1]^=(1<<padding)-1;}
 const answer=decode(payload,width);assert.equal(answer.code,0,'valid mixed frame '+f);
 assert.ok(answer.pcm.equals(expected.subarray(f*size,(f+1)*size)),'Mixed PCM after rejected calls '+f);
 if(meta.wideband)assert.equal(answer.callbacks,4);
}
cpu.data[command]=2;cpu.data[status]=0;until(()=>cpu.data[status]===1);
const fresh=decode(Buffer.from(raw.subarray(0,32)),data.packetLengths[0]);assert.equal(fresh.code,0);assert.ok(fresh.pcm.equals(expected.subarray(0,size)),'Reset first frame');
const report={backend:'asm',wideband:meta.wideband,binarySha256:meta.binarySha256,inputSha256:data.inputSha256,pcmSha256:data.pcmSha256,
 frames:data.frames,rejectedCalls:rejected,mixedEnabledModes:[1,2,8,3,4],paddingIgnored:true,resetExact:true,pcmExact:true,
 includesInterrupts:false,physicalBoardTested:false,flashBytes:binary.length,staticSramBytes:end-256,peakStack:2303-minSP,freeSram:minSP-end+1};
if(countMean)report.meanArithmetic={calls:meanCalls,hardwareMultiplies:meanMultiplies,
 hardwareMultipliesPerNb1Frame:640,exactDuringDecoder:true,rejectedCallsDoNotExecute:true};
if(countValues)report.noiseTableArithmetic={calls:valuesCalls,hardwareMultiplies:valuesMultiplies,
 callsPerNb1Frame:1,valuesPerCall:5,rejectedCallsDoNotExecute:true};
if(countFold)report.noiseFoldArithmetic={calls:foldCalls,hardwareMultiplies:foldMultiplies,
 transformedValuesPerNb1Frame:16,foldMulsPerNb1Frame:112,controllerMulsPerNb1Frame:116,rejectedCallsDoNotExecute:true};
if(countVocoder)report.vocoderArithmetic={calls:vocoderCalls,hardwareMultiplies:vocoderMultiplies,
 callsPerNb1Frame:4,hardwareMultipliesPerNb1Frame:640,rejectedCallsDoNotExecute:true,
 zeroContextDispatchAvailable:zeroVocoderAvailable,byPath:vocoderPaths,preparedContextDispatchExact:true};
if(countPrepare)report.framePreparationArithmetic={calls:prepareCalls,hardwareMultiplies:prepareMultiplies,
 perCall:prepareCounts,byGain:prepareGroups,rejectedCallsDoNotExecute:true};
if(countNb1Gain)report.nb1GainLookup={calls:gainLookups,codeHistogram:gainHistogram,exactFlashAddressPerFrame:true,
 originalFiniteMapVerified:true,invalidAndOtherModeCallsDoNotExecute:true};
if(countLowFusion)report.lowFusionArithmetic={byMode:lowStats,rejectedCallsAndOtherModesDoNotExecute:true,
 fourCallsPerMatchingWbFrame:true,nbApiDoesNotExecute:true};
if(countForcedZero)report.forcedZeroArithmetic={frames:zeroFrameCalls,twentyWordCalls:zeroVectorCalls,hardwareMultiplies:zeroFrameMuls,
 minMultipliesPerFrame:zeroMinMuls,maxMultipliesPerFrame:zeroMaxMuls,noAdaptiveKernel:true,noExcitationHistoryOrOutputReads:true,
 invalidAndNonzeroCoefficientCallsDoNotExecute:true};
if(countForcedOne)report.forcedOneArithmetic={frames:oneFrames,calls:oneCalls,samples:oneSamples,hardwareMultiplies:oneMuls,
 callsByCount:oneCounts,sixMulsPerSample:true,noThreeTapKernelForNb8:true,invalidOtherModeAndZeroCoefficientCallsDoNotExecute:true};
if(countForcedQ6)report.forcedQ6Arithmetic={calls:q6Calls,hardwareMultiplies:q6Muls,cycles:q6Cycles,cyclesPerCall:18,
 twoMulsPerCall:true,exactDuringDecoder:true,inputRegistersAndR1Preserved:true,exactAncestryCounts:true,
 invalidOtherModeAndZeroCoefficientCallsDoNotExecute:true};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS mixed API',JSON.stringify(report));
