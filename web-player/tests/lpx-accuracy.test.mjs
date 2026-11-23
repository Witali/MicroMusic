import test from'node:test';
import assert from'node:assert/strict';
import{readFileSync}from'node:fs';
import{spawnSync}from'node:child_process';
import{createEncoder}from'../lpx/encoder.js';
import{createDecoder,createIncrementalDecoder}from'../lpx/codec.js';
import{encodeStreaming}from'../lpx/streaming.js';
const read=async url=>readFileSync(url),load=async name=>createEncoder(readFileSync(new URL(`../lpx/encoder-adaptive${name}.wasm`,import.meta.url)));
const scalar=await load(''),simd=await load('-simd'),decoderBinary=readFileSync(new URL('../lpx/decoder.wasm',import.meta.url));
const decode=await createDecoder(decoderBinary),tone=n=>Int16Array.from({length:n},(_,i)=>Math.round(2000*Math.sin(i*.15)+500*Math.sin(i*.31)));
test('first correction charges all presence flags and retains a useful tight-budget subset',
 {skip:!process.env.LPX_ACCURACY_ALLOCATION_SCALAR||!process.env.LPX_ACCURACY_ALLOCATION_SIMD},async()=>{
 for(const file of[process.env.LPX_ACCURACY_ALLOCATION_SCALAR,process.env.LPX_ACCURACY_ALLOCATION_SIMD]){
  const{instance}=await WebAssembly.instantiate(readFileSync(file));instance.exports.__wasm_call_ctors();
  for(let i=0;i<3;i++)assert.equal(instance.exports.accuracy_allocation_selftest(),0);
 }
});
test('one accuracy engine accepts four levels at all rates and never treats P3/P8 as hard caps',()=>{
  const pcm=tone(641);
  for(const rate of[8000,12000,16000])for(const level of[3,4,6,8]){
    const options={accuracy:true,calls:0},a=scalar(pcm,rate,level,()=>{},options),b=simd(pcm,rate,level,()=>{},options);
    assert.deepEqual(a,b);const result=decode(a);assert.equal(result.samples,pcm.length);assert.equal(result.profile,level<=4?4:6);assert.equal(result.sampleRate,rate);
    if(level===3&&rate===8000)assert.ok(a.length>Math.floor(pcm.length*3/64),'quantization level is not the retired bitrate cap');
    for(const executable of[process.env.LPX_ACCURACY_NATIVE,process.env.LPX_ACCURACY_CUDA].filter(Boolean))for(const backend of executable===process.env.LPX_ACCURACY_CUDA?['cpu','cuda']:['cpu']){const native=spawnSync(executable,['--accuracy',String(level),'--rate',String(rate),'--quality','fast','--backend',backend],{input:Buffer.from(pcm.buffer),maxBuffer:1024*1024});assert.equal(native.status,0,native.stderr?.toString());assert.deepEqual(native.stdout,Buffer.from(a));}
  }
});
test('direct full P8 is deterministic and preserves perfect silence',()=>{
  for(const pcm of[tone(641),new Int16Array(641)]){
    const options={accuracy:true,calls:4},b=scalar(pcm,8000,8,()=>{},options);
    assert.deepEqual(b,simd(pcm,8000,8,()=>{},options));assert.equal(decode(b).samples,pcm.length);
    if(process.env.LPX_ACCURACY_CUDA)for(const backend of['cpu','cuda']){const native=spawnSync(process.env.LPX_ACCURACY_CUDA,['--accuracy','8','--rate','8000','--calls','4','--backend',backend],{input:Buffer.from(pcm.buffer),maxBuffer:1024*1024});assert.equal(native.status,0,native.stderr?.toString());assert.deepEqual(native.stdout,Buffer.from(b));}
    if(!pcm.some(x=>x!==0))assert.deepEqual(decode(b).pcm,pcm);
  }
});

test('every accuracy level keeps one continuous Long file, with exact P4/P6 fast compatibility',async()=>{
  const pcm=tone(65537),source=async(at,n)=>pcm.slice(at,at+n);
  for(const profile of[3,4,6,8]){
    const settings={samples:pcm.length,sampleRate:8000,profile,calls:0,accuracy:true};
    const result=await encodeStreaming(scalar,settings,source,()=>{},read);
    assert.deepEqual(result.bytes,(await encodeStreaming(simd,settings,source,()=>{},read)).bytes);
    assert.equal(decode(result.bytes).samples,pcm.length);assert.equal(result.long,true);
    if(profile===4||profile===6)assert.deepEqual(result.bytes,(await encodeStreaming(scalar,{...settings,accuracy:false},source,()=>{},read)).bytes);
  }
});
test('P4/P6 retain wire names while accuracy allocation uses the common pipeline',()=>{
  const pcm=tone(641);
  for(const profile of[4,6])for(const rate of[8000,12000,16000])
    {const bytes=scalar(pcm,rate,profile,()=>{},{accuracy:true});assert.deepEqual(bytes,simd(pcm,rate,profile,()=>{},{accuracy:true}));assert.equal(decode(bytes).profile,profile);}
});
test('continued P8 uses one direct session and retains all boundary samples',async()=>{
  const pcm=tone(20501),settings={samples:pcm.length,sampleRate:8000,accuracy:true,calls:0};
  let reads=0;const source=async(at,n)=>{reads++;return pcm.slice(at,at+n);};
  let sessions=0;const counted=(...args)=>scalar(...args);counted.createStream=s=>{sessions++;return scalar.createStream(s);};
  const upper=await encodeStreaming(counted,{...settings,profile:8},source,()=>{},read);
  assert.equal(sessions,1);assert.equal(reads,2);
  const other=await encodeStreaming(simd,{...settings,profile:8},source,()=>{},read);
  assert.deepEqual(upper.bytes,other.bytes);assert.equal(decode(upper.bytes).samples,pcm.length);assert.equal(upper.accuracyLevel,8);
});
test('incremental decoder keeps exact output across arbitrary reads, EOF corruption and reuse',async()=>{
  const open=await createIncrementalDecoder(decoderBinary);
  for(const count of[641,65537]){
    const bytes=scalar(tone(count),8000,4,()=>{},{accuracy:true,calls:0}),expected=decode(bytes).pcm;
    for(const width of[1,17,20480]){const stream=open(bytes);for(let at=0;at<count;at+=width){const n=Math.min(width,count-at);assert.deepEqual(stream.read(n),expected.slice(at,at+n));}assert.throws(()=>stream.read(1));}
    const broken=bytes.slice();broken[broken.length-1]^=128;
    assert.throws(()=>{const stream=open(broken);for(let at=0;at<count;at+=20480)stream.read(Math.min(20480,count-at));});
  }
});
