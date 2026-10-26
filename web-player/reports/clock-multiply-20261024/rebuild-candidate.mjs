// Rebuild the rejected experiment without editing the production checkout.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync,existsSync} from 'node:fs';
import {execFileSync,spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {dirname,resolve,join,relative,isAbsolute,parse,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
const retained=dirname(fileURLToPath(import.meta.url)),root=resolve(retained,'../../..');
const sha=b=>createHash('sha256').update(b).digest('hex');
const sourcePath='web-player/native/peripherals/device_clock.h';
const manifest=JSON.parse(readFileSync(join(retained,'native-manifest.json')));
const original=JSON.parse(execFileSync('git',['show','bb5f329:web-player/wasm/device-build.json'],{cwd:root}));
for(const key of ['flags','exports','sources','compilerVersion'])assert.deepEqual(manifest[key],original[key]);
assert.deepEqual(Object.keys(manifest.inputs).filter(path=>manifest.inputs[path]!==original.inputs[path]),[sourcePath]);
const parent=join(root,'build/rejected-clock-multiply-reproduction');mkdirSync(parent,{recursive:true});
const folder=mkdtempSync(join(parent,'rebuild-'));
for(const [path,expected] of Object.entries(manifest.inputs)){
  const source=(path===sourcePath?readFileSync(join(retained,'candidate-device-clock.h.txt')):
    execFileSync('git',['show','bb5f329:'+path],{cwd:root,maxBuffer:4*1024*1024})).toString('utf8').replaceAll('\r\n','\n');
  assert.equal(sha(source),expected,path);
  const target=resolve(folder,path),rel=relative(folder,target);
  assert.ok(rel&&!isAbsolute(rel)&&rel!=='..'&&!rel.startsWith('..'+sep));
  mkdirSync(dirname(target),{recursive:true});writeFileSync(target,source);
}
let sdk=process.env.EMSDK;
for(let at=root;!sdk;at=dirname(at)){
  const possible=join(at,'build/toolchains/emscripten-6.0.12');
  if(existsSync(possible))sdk=possible;
  if(at===parse(at).root)break;
}
assert.ok(sdk,'Set EMSDK to the pinned read-only SDK');
const compiler=join(sdk,'upstream/bin','clang'+(process.platform==='win32'?'.exe':''));
assert.equal(execFileSync(compiler,['--version'],{encoding:'utf8'}).split(/\r?\n/)[0],manifest.compilerVersion);
const wasm=join(folder,'attiny13a.wasm');
const args=[...manifest.flags.map(flag=>flag.replaceAll('<emsdk>',sdk)),...manifest.sources,'-lc','-lclang_rt.builtins','-o',wasm];
const run=spawnSync(compiler,args,{cwd:folder,encoding:'utf8'});assert.ifError(run.error);assert.equal(run.status,0,run.stderr);
const binary=readFileSync(wasm),recorded=readFileSync(join(retained,'candidate.wasm'));
assert.equal(sha(binary),manifest.artifacts['attiny13a.wasm']);assert.ok(binary.equals(recorded),'exact rejected binary reproduced');
assert.deepEqual(WebAssembly.Module.imports(new WebAssembly.Module(binary)),[]);
console.log('Exact rejected clock-multiply experiment rebuilt: '+sha(binary));console.log(wasm);
