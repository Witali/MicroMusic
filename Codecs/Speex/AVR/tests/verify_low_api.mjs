// Variable-size calls, all enabled modes, error guards, padding and reset.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {join,resolve} from 'node:path';
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
const vocoderEntry=countVocoder?address('speex_nb1_synthesize40_avr'):-1;
let vocoderActive=null,vocoderCalls=0,vocoderMultiplies=0;
const countPrepare=process.argv.includes('--count-noise-prepare');
const prepareNames=[...symbols.keys()].filter(n=>n==='speex_nb1_excitation_prepare'||n.startsWith('speex_nb1_excitation_prepare.'));
if(countPrepare)assert.equal(prepareNames.length,1,'NB1 frame preparation entry');
const prepareEntry=countPrepare?address(prepareNames[0]):-1;
let prepareActive=null,prepareCalls=0,prepareMultiplies=0;const prepareCounts=[];
const countLowFusion=process.argv.includes('--count-low-fusion'),lowEntries=new Map();
const lowStats={2:{calls:0,muls:0},8:{calls:0,muls:0}};let lowActive=null;
if(countLowFusion)for(const m of [2,8]){
 const name=`speex_wb_excitation_nb${m}_40_avr`;
 if(meta.wideband)assert.ok(symbols.has(name),name);
 if(symbols.has(name))lowEntries.set(address(name),m);
}
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
 if(cpu.pc*2===vocoderEntry){assert.equal(vocoderActive,null);vocoderActive={sp:cpu.SP,muls:0};}
 if(vocoderActive&&((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300))++vocoderActive.muls;
 if(cpu.pc*2===prepareEntry){assert.equal(prepareActive,null);prepareActive={sp:cpu.SP,muls:0};}
 if(prepareActive&&((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300))++prepareActive.muls;
 if(lowEntries.has(cpu.pc*2)){assert.equal(lowActive,null);lowActive={mode:lowEntries.get(cpu.pc*2),sp:cpu.SP,muls:0};}
 if(lowActive&&((opcode&0xfc00)===0x9c00||(opcode&0xff00)===0x0200||(opcode&0xff88)===0x0300))++lowActive.muls;
 avrInstruction(cpu);cpu.tick();minSP=Math.min(minSP,cpu.SP);assert.ok(cpu.SP>=end,'SRAM collision');
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
  ++vocoderCalls;vocoderMultiplies+=vocoderActive.muls;vocoderActive=null;
 }
 if(prepareActive&&opcode===0x9508&&cpu.SP===prepareActive.sp+2){
  assert.equal(cpu.data[1],0);++prepareCalls;prepareMultiplies+=prepareActive.muls;prepareCounts.push(prepareActive.muls);prepareActive=null;
 }
 if(lowActive&&opcode===0x9508&&cpu.SP===lowActive.sp+2){
  assert.equal(lowActive.muls,lowActive.mode===2?604:602);assert.equal(cpu.data[1],0);
  ++lowStats[lowActive.mode].calls;lowStats[lowActive.mode].muls+=lowActive.muls;lowActive=null;
 }
 if(meta.wideband&&cpu.data[chunks]!==lastChunk){lastChunk=cpu.data[chunks];const at=cpu.dataView.getUint16(pcm,true);output.push(Buffer.from(cpu.data.subarray(at,at+160)));}
}}
until(()=>cpu.data[status]===1);
function decode(payload,width,invalidFlags=0){
 const callsBefore=meanCalls,valuesBefore=valuesCalls,foldBefore=foldCalls,vocoderBefore=vocoderCalls,prepareBefore=prepareCalls;
 const lowBefore={2:lowStats[2].calls,8:lowStats[8].calls};
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
 callsPerNb1Frame:4,hardwareMultipliesPerNb1Frame:640,rejectedCallsDoNotExecute:true};
if(countPrepare)report.framePreparationArithmetic={calls:prepareCalls,hardwareMultiplies:prepareMultiplies,
 perCall:prepareCounts,rejectedCallsDoNotExecute:true};
if(countLowFusion)report.lowFusionArithmetic={byMode:lowStats,rejectedCallsAndOtherModesDoNotExecute:true,
 fourCallsPerMatchingWbFrame:true,nbApiDoesNotExecute:true};
writeFileSync(join(dir,'verification.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS mixed API',JSON.stringify(report));
