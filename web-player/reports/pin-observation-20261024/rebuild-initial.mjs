// Reproduce the retained initial two-ring checkpoint without editing production.
import assert from 'node:assert/strict';
import {execFileSync,spawnSync} from 'node:child_process';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,dirname,join,parse} from 'node:path';
import {fileURLToPath} from 'node:url';

const root=fileURLToPath(new URL('../../../',import.meta.url));
const manifest=JSON.parse(readFileSync(new URL('./initial-native-manifest.json',import.meta.url)));
const report=JSON.parse(readFileSync(new URL('./initial-benchmark.json',import.meta.url)));
const ref=report.git.baselineCommit,out=resolve(root,'build/pin-observation-initial-rebuilt');
const sha=b=>createHash('sha256').update(b).digest('hex');
const normalized=path=>readFileSync(path,'utf8').replaceAll('\r\n','\n');
mkdirSync(out,{recursive:true});
for(const path of Object.keys(manifest.inputs)){
  const target=join(out,path);mkdirSync(dirname(target),{recursive:true});
  writeFileSync(target,execFileSync('git',['show',ref+':'+path],{cwd:root,maxBuffer:16*1024*1024}));
}
execFileSync('git',['apply','--unsafe-paths','--directory='+out,
  fileURLToPath(new URL('./initial-native.patch',import.meta.url))],{cwd:root});
for(const [path,expected] of Object.entries(manifest.inputs))
  assert.equal(sha(normalized(join(out,path))),expected,path);
let sdk=process.env.EMSDK;
for(let parent=root;!sdk;parent=dirname(parent)){
  const candidate=join(parent,'build/toolchains/emscripten-6.0.12');
  if(existsSync(join(candidate,'upstream/bin/clang.exe')))sdk=candidate;
  if(parent===parse(parent).root)break;
}
assert.ok(sdk,'Prepared SDK required');sdk=resolve(sdk);
const clang=join(sdk,'upstream/bin',process.platform==='win32'?'clang.exe':'clang');
const version=execFileSync(clang,['--version'],{encoding:'utf8'}).split(/\r?\n/)[0];
assert.equal(version,manifest.compilerVersion);
const target=join(out,'attiny13a.wasm');
const build=spawnSync(clang,[...manifest.flags.map(flag=>flag.replaceAll('<emsdk>',sdk)),
  ...manifest.sources,'-lc','-lclang_rt.builtins','-o',target],{cwd:out,encoding:'utf8'});
assert.equal(build.status,0,build.stderr||String(build.error));
const binary=readFileSync(target);assert.equal(binary.length,manifest.bytes);
assert.equal(sha(binary),manifest.artifacts['attiny13a.wasm']);
const module=new WebAssembly.Module(binary);assert.deepEqual(WebAssembly.Module.imports(module),[]);
assert.equal(new WebAssembly.Instance(module).exports.memory.buffer.byteLength,131072);
writeFileSync(join(out,'device-build.json'),JSON.stringify(manifest,null,2)+'\n');
console.log('Exact initial runtime reproduced: '+sha(binary)+' in '+out);
