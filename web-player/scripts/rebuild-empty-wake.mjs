// Reproduce one wake-delay candidate in build/ without editing production.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {execFileSync,spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {resolve,join,dirname,relative,isAbsolute,parse,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{'out-dir':{type:'string',default:'build/empty-wake-20261101'},emsdk:{type:'string'}}});
const out=resolve(root,values['out-dir']),local=relative(resolve(root,'build'),out);
assert.ok(local&&!isAbsolute(local)&&local!=='..'&&!local.startsWith('..'+sep),'Keep generated sources in build/');
const shadow=join(out,'shadow'),baseline='9e8909ff',path='web-player/native/peripherals/device.c';
const git=p=>execFileSync('git',['show',baseline+':'+p],{cwd:root,maxBuffer:8*1024*1024});
const sha=b=>createHash('sha256').update(b).digest('hex'),normalize=b=>b.toString().replaceAll('\r\n','\n');
const manifest=JSON.parse(git('web-player/wasm/device-build.json'));
let sdk=values.emsdk||process.env.EMSDK;
for(let parent=root;!sdk;parent=dirname(parent)){
  const candidate=join(parent,'build/toolchains/emscripten-6.0.12');
  if(existsSync(join(candidate,'upstream/bin/clang.exe')))sdk=candidate;
  if(parent===parse(parent).root)break;
}
assert.ok(sdk,'Pass the registered SDK');sdk=resolve(sdk);
for(const [p,expected]of Object.entries(manifest.inputs)){
  assert.ok(!isAbsolute(p)&&!p.replaceAll('\\','/').split('/').includes('..'));
  const bytes=git(p);assert.equal(sha(normalize(bytes)),expected);
  const target=join(shadow,p);mkdirSync(dirname(target),{recursive:true});writeFileSync(target,bytes);
}
const folder=join(shadow,'web-player/wasm');mkdirSync(folder,{recursive:true});const binary=join(folder,'attiny13a.wasm');
const compiler=join(sdk,'upstream/bin',process.platform==='win32'?'clang.exe':'clang');
const build=()=>{
  const r=spawnSync(compiler,[...manifest.flags.map(f=>f.replaceAll('<emsdk>',sdk)),...manifest.sources,
    '-lc','-lclang_rt.builtins','-o',binary],{cwd:shadow,encoding:'utf8'});
  assert.equal(r.status,0,r.stderr||String(r.error));return readFileSync(binary);
};
const original=git('web-player/wasm/attiny13a.wasm'),control=build();assert.ok(control.equals(original),'Control rebuild differs');
writeFileSync(join(out,'control-native.wasm'),control);
let source=normalize(git(path));
const before=`  uint64_t fuse_startup=source_duration(12);
  if (board.config[DEVICE_CFG_FUSE_STARTUP_PROFILE] &&
      board.sleep.mode==SYSTEM_SLEEP_POWER_DOWN && startup<fuse_startup) startup=fuse_startup;`;
const after=`  uint64_t extra=0;
  if (pending) {
   uint64_t fuse_startup=source_duration(12);
   if (board.config[DEVICE_CFG_FUSE_STARTUP_PROFILE] &&
       board.sleep.mode==SYSTEM_SLEEP_POWER_DOWN && startup<fuse_startup) startup=fuse_startup;
   extra=source_duration(8u*board.divisor);
  }`;
assert.equal(source.split(before).length,2);source=source.replace(before,after);
const call='startup,source_duration(8u*board.divisor),board.base);';
assert.equal(source.split(call).length,2);source=source.replace(call,'startup,extra,board.base);');
writeFileSync(join(shadow,path),source);writeFileSync(join(out,'candidate-device.c'),source);
const bytes=build(),module=new WebAssembly.Module(bytes);assert.deepEqual(WebAssembly.Module.imports(module),[]);
assert.deepEqual(WebAssembly.Module.exports(module).filter(e=>e.kind==='function').map(e=>e.name).sort(),[...manifest.exports].sort());
const e=new WebAssembly.Instance(module).exports;assert.equal(e.memory.buffer.byteLength,131072);assert.throws(()=>e.memory.grow(1),RangeError);
const candidateManifest={...manifest,inputs:{...manifest.inputs,[path]:sha(source)},artifacts:{'attiny13a.wasm':sha(bytes)},bytes:bytes.length};
writeFileSync(join(folder,'device-build.json'),JSON.stringify(candidateManifest,null,2)+'\n');
const proof={schema:'micromusic-empty-wake-build-v1',baseline,controlByteEqual:true,controlSha256:sha(control),
  candidateSha256:sha(bytes),candidateBytes:bytes.length,deviceSourceSha256:sha(source),imports:0,exports:manifest.exports.length,
  memoryPages:2,maximumMemoryPages:2,sourceCount:manifest.sources.length};
writeFileSync(join(out,'build-proof.json'),JSON.stringify(proof,null,2)+'\n');console.log(JSON.stringify(proof));
