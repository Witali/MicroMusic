// Builds isolated numerical test seams, without changing shipped binaries.
import {spawnSync} from 'node:child_process';
import {readFileSync,mkdirSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';

const {values}=parseArgs({options:{emsdk:{type:'string'},'legacy-root':{type:'string'}}});
const root=fileURLToPath(new URL('../../',import.meta.url));
const sdk=values.emsdk||process.env.EMSDK;
if(!sdk)throw new Error('Pass --emsdk <SDK directory> or set EMSDK; it is read only.');
const compiler=join(resolve(sdk),'upstream/bin',process.platform==='win32'?'clang.exe':'clang');
const sysroot=join(resolve(sdk),'upstream/emscripten/cache/sysroot');
const manifest=JSON.parse(readFileSync(join(root,'web-player/lpx/encoder-adaptive-build.json')));
const flags=manifest.flags.filter(flag=>!flag.startsWith('-Wl,--export='))
  .map(flag=>flag.replaceAll('<emsdk>/upstream/emscripten/cache/sysroot',sysroot));
const exports=['__wasm_call_ctors','quality_reserve','quality_reference','quality_candidate','quality_measure',
  'quality_resample','quality_analysis','quality_fullband','quality_fullband_selftest'];
const host='Codecs/LPX/01_ACTIVE_Q0_CODEC/host/';
mkdirSync(join(root,'build'),{recursive:true});
function build(name,extra,qualityRoot=host) {
  const args=[...extra,...flags,...exports.map(name=>'-Wl,--export='+name),
    qualityRoot+'LpxQuality.cpp',qualityRoot+'LpxStoi.cpp',host+'LpxAdaptiveDsp.cpp',
    host+'LpxFullBand.cpp',host+'LpxWasmMemory.cpp','web-player/tests/helpers/lpx-quality-native.cpp',
    '-L'+join(sysroot,'lib/wasm32-emscripten'),'-lc++-noexcept','-lc++abi-noexcept','-lc','-lclang_rt.builtins',
    '-o',join(root,'build/'+name+'.wasm')];
  const done=spawnSync(compiler,args,{cwd:root,encoding:'utf8'});
  if(done.error)throw done.error;
  if(done.status!==0)throw new Error(done.stderr||done.stdout);
  console.log('build/'+name+'.wasm');
}
build('lpx-quality-selftest',[]);
build('lpx-quality-simd-selftest',['-msimd128','-DLPX_ENCODER_SIMD_SEARCH=1']);
if(values['legacy-root'])build('lpx-quality-legacy-selftest',
  ['-DLPX_QUALITY_LEGACY=1','-I'+values['legacy-root']],values['legacy-root'].replace(/[\\/]?$/,'/'));
