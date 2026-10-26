import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {execFileSync,spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {join,dirname} from 'node:path';
const root=fileURLToPath(new URL('../../../',import.meta.url)),dir=fileURLToPath(new URL('./',import.meta.url));
const sha=b=>createHash('sha256').update(b).digest('hex'),norm=b=>b.toString().replaceAll('\r\n','\n');
const read=p=>readFileSync(join(dir,p)),record=JSON.parse(read('verification.json')),evidence=JSON.parse(read('evidence.json'));
const cache=new Map(),git=(ref,p)=>{const key=ref+':'+p;if(!cache.has(key))cache.set(key,execFileSync('git',['show',key],{cwd:root,maxBuffer:16*1024*1024}));return cache.get(key);};
for(const [p,h]of Object.entries(evidence.filesSha256))assert.equal(sha(p.endsWith('.gz')?read(p):norm(read(p))),h,p);
const manifest=JSON.parse(git(record.sourceCommit,'web-player/wasm/device-build.json'));
for(const [p,h]of Object.entries(record.sourceSha256))assert.equal(sha(norm(git(record.sourceCommit,p))),h,p);
for(const [p,h]of Object.entries(manifest.inputs))assert.equal(record.sourceSha256[p],h,p+' native provenance');
const binary=git(record.sourceCommit,'web-player/wasm/attiny13a.wasm');
assert.ok(binary.equals(git(record.baseline,'web-player/wasm/attiny13a.wasm')));assert.equal(sha(binary),record.runtimeSha256);
assert.equal(sha(binary),manifest.artifacts['attiny13a.wasm']);assert.equal(binary.length,record.bytes);assert.equal(record.binaryByteEqual,true);
const module=new WebAssembly.Module(binary);assert.deepEqual(WebAssembly.Module.imports(module),[]);
assert.equal(new WebAssembly.Instance(module).exports.memory.buffer.byteLength,131072);
for(const [p,count]of [['full-test.tap.gz',record.fullTests],['focused-test.tap.gz',record.focusedTests]])
  assert.match(gunzipSync(read(p)).toString(),new RegExp('# tests '+count+'\\r?\\n# suites 0\\r?\\n# pass '+count+'\\r?\\n# fail 0'));
const bindings=norm(git(record.sourceCommit,'web-player/native/devices/attiny13a/io_registers.inc'));
const entries=[...bindings.matchAll(/^AT13_IO_(PUBLISH|LOCAL)\(([A-Z0-9_]+),\s*([A-Z0-9_]+)/gm)];
assert.equal(entries.length,record.ioOwners);assert.equal(entries.filter(e=>e[1]==='PUBLISH').length,record.publishedBytes);
assert.equal(entries.filter(e=>e[2]==='TIMER0').length,record.timerRoutes);
if(process.argv.includes('--check-current')){
  assert.ok(readFileSync(join(root,'web-player/wasm/attiny13a.wasm')).equals(binary));
  for(const p of Object.keys(manifest.inputs))assert.equal(sha(norm(readFileSync(join(root,p)))),record.sourceSha256[p],p+' current source');
}
if(process.argv.includes('--rebuild')){
  const parent=join(root,'build/replays');mkdirSync(parent,{recursive:true});const target=mkdtempSync(join(parent,'io-owners-'));
  for(const p of Object.keys(record.sourceSha256)){
    const path=join(target,p);mkdirSync(dirname(path),{recursive:true});writeFileSync(path,git(record.sourceCommit,p));
  }
  writeFileSync(join(target,'package.json'),'{"type":"module"}\n');
  const build=spawnSync(process.execPath,[join(target,'web-player/scripts/build-device-wasm.mjs')],{cwd:target,encoding:'utf8'});
  assert.equal(build.status,0,build.stderr||build.stdout);assert.ok(readFileSync(join(target,'web-player/wasm/attiny13a.wasm')).equals(binary),'isolated build bytes');
  const tests=spawnSync(process.execPath,['--test',join(target,'web-player/tests/device-io-owners.test.mjs')],{cwd:target,encoding:'utf8'});
  assert.equal(tests.status,0,tests.stderr||tests.stdout);assert.match(tests.stdout,/# pass 4/);
  writeFileSync(join(target,'rebuild.log'),build.stdout+'\n'+tests.stdout);console.log('Isolated identical WASM and four ownership tests: '+target);
}
console.log(JSON.stringify({sourceCommit:record.sourceCommit,bytes:binary.length,runtimeSha256:record.runtimeSha256,ioOwners:entries.length,tests:record.fullTests}));
