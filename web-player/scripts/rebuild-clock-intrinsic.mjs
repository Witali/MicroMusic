// Reconstruct the rejected checked-overflow experiment without touching production.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {execFileSync,spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {resolve,join,dirname,relative,isAbsolute,parse,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{'out-dir':{type:'string',default:'build/clock-intrinsic-rebuild'},emsdk:{type:'string'}}});
const out=resolve(root,values['out-dir']),local=relative(resolve(root,'build'),out);
assert.ok(local&&!isAbsolute(local)&&local!=='..'&&!local.startsWith('..'+sep),'Keep generated sources in build/');
const shadow=join(out,'shadow'),baseline='103ca59a',header='web-player/native/peripherals/device_clock.h';
const git=path=>execFileSync('git',['show',baseline+':'+path],{cwd:root,maxBuffer:8*1024*1024});
const sha=b=>createHash('sha256').update(b).digest('hex'),normalize=b=>b.toString().replaceAll('\r\n','\n');
const manifest=JSON.parse(git('web-player/wasm/device-build.json'));
let sdk=values.emsdk||process.env.EMSDK;
for(let parent=root;!sdk;parent=dirname(parent)){
  const candidate=join(parent,'build/toolchains/emscripten-6.0.12');
  if(existsSync(join(candidate,'upstream/bin/clang.exe')))sdk=candidate;
  if(parent===parse(parent).root)break;
}
assert.ok(sdk,'Pass --emsdk for the registered toolchain');sdk=resolve(sdk);
for(const [path,expected]of Object.entries(manifest.inputs)){
  assert.ok(!isAbsolute(path)&&!path.replaceAll('\\','/').split('/').includes('..'));
  const bytes=git(path);assert.equal(sha(normalize(bytes)),expected);
  const target=join(shadow,path);mkdirSync(dirname(target),{recursive:true});writeFileSync(target,bytes);
}
const folder=join(shadow,'web-player/wasm');mkdirSync(folder,{recursive:true});const binary=join(folder,'attiny13a.wasm');
const compiler=join(sdk,'upstream/bin',process.platform==='win32'?'clang.exe':'clang');
const build=()=>{
  const run=spawnSync(compiler,[...manifest.flags.map(f=>f.replaceAll('<emsdk>',sdk)),...manifest.sources,
    '-lc','-lclang_rt.builtins','-o',binary],{cwd:shadow,encoding:'utf8'});
  assert.equal(run.status,0,run.stderr||String(run.error));return readFileSync(binary);
};
const original=git('web-player/wasm/attiny13a.wasm'),control=build();assert.ok(control.equals(original),'Control rebuild differs');
writeFileSync(join(out,'control-native.wasm'),control);
const before=' if (!b || a<=(UINT64_MAX-carry)/b) {\n  uint64_t n=a*b+carry;';
const after=' uint64_t n;\n if (!__builtin_mul_overflow(a,b,&n) && !__builtin_add_overflow(n,carry,&n)) {';
const source=normalize(git(header));assert.equal(source.split(before).length,2);
const candidateHeader=source.replace(before,after);writeFileSync(join(shadow,header),candidateHeader);
writeFileSync(join(out,'candidate-device-clock.h'),candidateHeader);
const bytes=build();assert.equal(sha(bytes),'19b325dc8a79730a7c9cb197879b838ff6f5f6d61312aed9bd830529cc438e1f','Different candidate/toolchain');
const module=new WebAssembly.Module(bytes);assert.deepEqual(WebAssembly.Module.imports(module),[]);
assert.deepEqual(WebAssembly.Module.exports(module).filter(e=>e.kind==='function').map(e=>e.name).sort(),[...manifest.exports].sort());
const instance=new WebAssembly.Instance(module);assert.equal(instance.exports.memory.buffer.byteLength,131072);
assert.throws(()=>instance.exports.memory.grow(1),RangeError);
const candidateManifest={...manifest,inputs:{...manifest.inputs,[header]:sha(candidateHeader)},
  artifacts:{'attiny13a.wasm':sha(bytes)},bytes:bytes.length};
writeFileSync(join(folder,'device-build.json'),JSON.stringify(candidateManifest,null,2)+'\n');
const proof={schema:'micromusic-clock-intrinsic-build-v1',baseline,controlByteEqual:true,controlSha256:sha(control),
  candidateSha256:sha(bytes),candidateBytes:bytes.length,headerSha256:sha(candidateHeader),imports:0,exports:manifest.exports.length,
  memoryPages:2,maximumMemoryPages:2,sourceCount:manifest.sources.length};
writeFileSync(join(out,'build-proof.json'),JSON.stringify(proof,null,2)+'\n');console.log(JSON.stringify(proof));
