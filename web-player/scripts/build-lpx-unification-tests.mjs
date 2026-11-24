// Link the production host core with narrow ownership/cache contract checks.
import {readFileSync,mkdirSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {resolve,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
const {values}=parseArgs({options:{emsdk:{type:'string'}}});
const root=fileURLToPath(new URL('../../',import.meta.url)),sdk=values.emsdk||process.env.EMSDK;
if(!sdk)throw Error('Pass --emsdk <SDK directory> (read only).');
const sysroot=join(resolve(sdk),'upstream/emscripten/cache/sysroot');
const compiler=join(resolve(sdk),'upstream/bin',process.platform==='win32'?'clang.exe':'clang');
const manifest=JSON.parse(readFileSync(join(root,'web-player/lpx/encoder-adaptive-build.json')));
const sources=Object.keys(manifest.inputs).filter(p=>p.endsWith('.cpp'));
const flags=manifest.flags.filter(f=>!f.startsWith('-Wl,--export=')).map(f=>f.replaceAll('<emsdk>/upstream/emscripten/cache/sysroot',sysroot));
mkdirSync(join(root,'build'),{recursive:true});
for(const [mode,extra] of [['scalar',[]],['simd',['-msimd128','-DLPX_ENCODER_SIMD_SEARCH=1']]]) {
  const args=[...flags,...extra,'-Wl,--export=__wasm_call_ctors','-Wl,--export=unification_selftest','-Wl,--export=seed_context_selftest',...sources,
    'web-player/tests/helpers/lpx-unification-selftest.cpp','-L'+join(sysroot,'lib/wasm32-emscripten'),
    '-lc++-noexcept','-lc++abi-noexcept','-lc','-lclang_rt.builtins','-o',join(root,`build/lpx-unification-${mode}.wasm`)];
  const result=spawnSync(compiler,args,{cwd:root,encoding:'utf8'});
  if(result.status!==0)throw Error(result.stderr||result.error?.message);
  console.log(`Built ${mode} unification contracts.`);
}
