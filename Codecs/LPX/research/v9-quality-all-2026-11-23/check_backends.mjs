// Re-encode frozen prepared inputs; no audio conversion or objective fitting.
// All paths/identities stay private. Print only anonymous numeric counts.
import assert from 'node:assert/strict';
import {readFileSync,realpathSync} from 'node:fs';
import {resolve,join,sep,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {spawnSync} from 'node:child_process';
import {createDecoder} from '../../../../web-player/lpx/codec.js';

const {values}=parseArgs({options:{manifest:{type:'string'},baseline:{type:'string'},
  candidate:{type:'string'},native:{type:'string'},cuda:{type:'string'},all:{type:'boolean',default:false},
  limit:{type:'string'}}});
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../../..');
function privatePath(path) {
  const absolute=realpathSync(resolve(root,path));
  assert.ok(absolute.startsWith(realpathSync(join(root,'build'))+sep),'Expected a private build artifact');
  return absolute;
}
const read=path=>JSON.parse(readFileSync(privatePath(path),'utf8'));
assert.ok(values.manifest&&values.baseline&&values.candidate);
const manifestPath=privatePath(values.manifest),manifest=read(manifestPath);
const baseline=privatePath(values.baseline),candidate=privatePath(values.candidate);
const apis=[];
for(const name of ['encoder-adaptive','encoder-adaptive-simd']) {
  const {instance}=await WebAssembly.instantiate(readFileSync(join(root,`web-player/lpx/${name}.wasm`)));
  instance.exports.__wasm_call_ctors();apis.push(instance.exports);
}
const decode=await createDecoder(readFileSync(join(root,'web-player/lpx/decoder.wasm')));
let jobs=0,wasm=0,cpu=0,cuda=0;
for(const job of manifest.jobs) {
  const receipt=read(join(candidate,job.job_id+'.json'));
  const old=read(join(baseline,job.job_id+'.json'));
  if(!values.all&&receipt.stream_sha256===old.stream_sha256)continue;
  if(values.limit&&jobs>=Number(values.limit))break;
  assert.equal(job.auto_quiet,false);assert.equal(job.normalize,false);
  assert.equal(job.calls,4);assert.equal(job.size_allowance_percent,0);
  const input=readFileSync(privatePath(resolve(dirname(manifestPath),job.target)));assert.equal(input.length,job.samples*2);
  const pcm=Int16Array.from({length:job.samples},(_,i)=>input.readInt16LE(i*2));
  const expected=readFileSync(privatePath(join(candidate,job.job_id+'.lpx')));
  const preset=job.mode==='k3'||job.mode==='k8',profile=job.mode==='p4'?4:6;
  for(const api of apis) {
    assert.equal(api.enc_reserve(job.samples),1);
    new Int16Array(api.memory.buffer,api.enc_input(),job.samples).set(pcm);
    const size=preset?api.enc_bitrate(job.samples,Number(job.mode.slice(1)),job.sample_rate,0,job.calls)
      :api.enc_adaptive_extended(job.samples,profile,job.sample_rate,0,receipt.driver.legacy_cap,job.calls,0);
    assert.ok(size>=13,'Encoder failed');
    const bytes=Buffer.from(new Uint8Array(api.memory.buffer,api.enc_adaptive_output(),size));
    assert.ok(bytes.equals(expected),`WASM ${job.mode}/${job.sample_rate}`);++wasm;
  }
  const decoded=decode(expected);
  assert.equal(decoded.samples,job.samples);assert.equal(decoded.sampleRate,job.sample_rate);
  assert.ok(Buffer.from(decoded.pcm.buffer).equals(readFileSync(privatePath(join(candidate,job.job_id+'.s16le')))));
  // The native PC CLI exposes P4/P6. Strict preset C++ API output is already
  // supplied by the frozen GCC driver; do not mislabel a different CLI search.
  if(!preset)for(const [key,accelerated] of [['native',false],['cuda',true]])if(values[key]) {
    const args=['--profile',String(profile),'--rate',String(job.sample_rate),'--max-bytes',String(receipt.driver.legacy_cap),
      '--calls',String(job.calls),...(accelerated?['--backend','cuda']:[])];
    const done=spawnSync(privatePath(values[key]),args,{input,maxBuffer:128*1024*1024});
    assert.equal(done.status,0,'Native encoder failed');
    assert.ok(done.stdout.equals(expected),`Native ${job.mode}/${job.sample_rate}`);
    if(accelerated)++cuda;else ++cpu;
  }
  ++jobs;
}
assert.ok(jobs>0,'No jobs selected');
console.log(JSON.stringify({jobs,wasm_encodes:wasm,windows_cpu_encodes:cpu,cuda_encodes:cuda,
  frozen_gcc_and_wasm_bytes_exact:true,wasm_pcm_exact:true}));
