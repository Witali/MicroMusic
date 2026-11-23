// Check final decoder compatibility against frozen private native receipts.
// No encoding, input-level changes, alignment, audio upload or source ranking.
import assert from 'node:assert/strict';
import {readFileSync,readdirSync,realpathSync} from 'node:fs';
import {resolve,join,sep,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {createDecoder} from '../../../../web-player/lpx/codec.js';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../../..');
const build=realpathSync(join(root,'build'))+sep;
function pathOf(path) {const value=realpathSync(resolve(root,path));assert.ok(value.startsWith(build));return value;}
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const decode=await createDecoder(readFileSync(join(root,'web-player/lpx/decoder.wasm')));
const directories=process.argv.slice(2);assert.ok(directories.length);
let jobs=0,samples=0;
for(const name of directories) {
  const directory=pathOf(name);
  for(const file of readdirSync(directory).filter(x=>/^case-\d+-(?:p[46]|k[38])-\d+\.json$/.test(x)).sort()) {
    const receipt=JSON.parse(readFileSync(pathOf(join(directory,file)),'utf8'));
    const stem=join(directory,file.slice(0,-5));
    const bytes=readFileSync(pathOf(stem+'.lpx')),expected=readFileSync(pathOf(stem+'.s16le'));
    const pwm=readFileSync(pathOf(stem+'.u8'));
    assert.equal(hash(bytes),receipt.stream_sha256);assert.equal(hash(expected),receipt.pcm_sha256);
    assert.equal(hash(pwm),receipt.pwm_sha256);
    const result=decode(bytes);
    assert.equal(result.samples,receipt.job.samples);assert.equal(result.sampleRate,receipt.job.sample_rate);
    assert.ok(Buffer.from(result.pcm.buffer).equals(expected),'Final decoder changed the frozen PCM');
    assert.equal(pwm.length,result.samples);
    for(let i=0;i<pwm.length;++i) {
      const q14=(result.pcm[i]+1)>>1;
      assert.equal(Math.max(0,Math.min(255,128+((q14*130+8192)>>14))),pwm[i]);
    }
    ++jobs;samples+=result.samples;
  }
}
assert.ok(jobs);
console.log(JSON.stringify({jobs,samples,final_wasm_native_pcm_exact:true,final_pwm_exact:true}));
