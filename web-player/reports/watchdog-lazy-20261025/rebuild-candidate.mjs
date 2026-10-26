// Rebuild the watchdog-lazy experiment without editing the production checkout.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync,existsSync} from 'node:fs';
import {execFileSync,spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {dirname,resolve,join,relative,isAbsolute,parse,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
const retained=dirname(fileURLToPath(import.meta.url)),root=resolve(retained,'../../..');
const sha=b=>createHash('sha256').update(b).digest('hex');
const adaptations={'web-player/native/peripherals/device.c':'candidate-device.c.txt','web-player/native/devices/attiny13a/clki_board.inc':'candidate-clki-board.inc.txt'};
const manifest=JSON.parse(readFileSync(join(retained,'native-manifest.json')));
const original=JSON.parse(execFileSync('git',['show','2c52cc1:web-player/wasm/device-build.json'],{cwd:root}));
for(const key of ['flags','exports','sources','compilerVersion'])assert.deepEqual(manifest[key],original[key]);
assert.deepEqual(Object.keys(manifest.inputs).filter(path=>manifest.inputs[path]!==original.inputs[path]),Object.keys(adaptations));
const parent=join(root,'build/watchdog-lazy-reproduction');mkdirSync(parent,{recursive:true});
const folder=mkdtempSync(join(parent,'rebuild-'));
for(const [path,expected] of Object.entries(manifest.inputs)){
  const source=(adaptations[path]?readFileSync(join(retained,adaptations[path])):
    execFileSync('git',['show','2c52cc1:'+path],{cwd:root,maxBuffer:4*1024*1024})).toString('utf8').replaceAll('\r\n','\n');
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
assert.equal(sha(binary),manifest.artifacts['attiny13a.wasm']);assert.ok(binary.equals(recorded),'exact candidate binary reproduced');
assert.deepEqual(WebAssembly.Module.imports(new WebAssembly.Module(binary)),[]);
console.log('Exact watchdog-lazy experiment rebuilt: '+sha(binary));console.log(wasm);
