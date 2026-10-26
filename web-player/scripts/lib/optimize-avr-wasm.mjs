// Offline only: no Binaryen dependency or optimizer work enters audio playback.
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {existsSync,mkdtempSync,readFileSync,writeFileSync,rmSync} from 'node:fs';
import {dirname,join,parse,resolve} from 'node:path';
import {tmpdir} from 'node:os';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';

export function findWasmOpt(explicit){
  if(explicit)return resolve(explicit);
  if(process.env.MICROMUSIC_WASM_OPT)return resolve(process.env.MICROMUSIC_WASM_OPT);
  const executable=process.platform==='win32'?'wasm-opt.exe':'wasm-opt';
  for(let directory=fileURLToPath(new URL('../../../',import.meta.url));;directory=dirname(directory)){
    const candidate=join(directory,'build/toolchains/emscripten-6.0.12/upstream/bin',executable);
    if(existsSync(candidate))return candidate;
    if(directory===parse(directory).root)return null;
  }
}
export function optimizeAVRWasm(generated,{level='O3',wasmOpt}={}){
  if(!['O2','O3','Os','Oz'].includes(level))throw Error('Optimization level must be O2, O3, Os or Oz');
  const executable=findWasmOpt(wasmOpt);
  if(!executable)throw Error('wasm-opt not found: use --wasm-opt or MICROMUSIC_WASM_OPT');
  const run=args=>{
    const result=spawnSync(executable,args,{encoding:'utf8',windowsHide:true,timeout:120000,maxBuffer:1024*1024});
    if(result.error)throw result.error;
    if(result.status!==0)throw Error('wasm-opt failed: '+(result.stderr||result.stdout||result.status));
    return result.stdout.trim();
  };
  const version=run(['--version']),before=new WebAssembly.Module(generated.bytes);
  const embedded=module=>{
    const sections=WebAssembly.Module.customSections(module,'micromusic.avr');
    assert.equal(sections.length,1,'Exactly one AVR manifest is required');
    return new Uint8Array(sections[0]);
  };
  assert.deepEqual(JSON.parse(new TextDecoder().decode(embedded(before))),generated.manifest,'Input manifest mismatch');
  const directory=mkdtempSync(join(tmpdir(),'micromusic-avr-opt-'));
  // Mutable exported globals are already part of the generated runtime ABI.
  // Keep the complete bridge import set required by existing package versions.
  // No fast-math, trap assumptions, zero-memory assumptions or closed-world.
  const flags=['-'+level,'--mvp-features','--enable-mutable-globals','--skip-pass=remove-unused-module-elements'];
  try{
    const input=join(directory,'input.wasm'),output=join(directory,'output.wasm');
    writeFileSync(input,generated.bytes);const start=performance.now();
    run([input,...flags,'-o',output]);const elapsedMs=performance.now()-start;
    const bytes=new Uint8Array(readFileSync(output)),after=new WebAssembly.Module(bytes);
    assert.deepEqual(WebAssembly.Module.imports(after),WebAssembly.Module.imports(before),'Optimizer changed AVR imports');
    const exports=module=>WebAssembly.Module.exports(module).sort((a,b)=>a.name.localeCompare(b.name));
    assert.deepEqual(exports(after),exports(before),'Optimizer changed AVR exports');
    assert.deepEqual(embedded(after),embedded(before),'Optimizer changed AVR manifest');
    const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
    return {...generated,bytes,optimization:{tool:version,executableSha256:hash(readFileSync(executable)),flags,
      inputSha256:hash(generated.bytes),outputSha256:hash(bytes),inputBytes:generated.bytes.length,outputBytes:bytes.length,elapsedMs}};
  }finally{
    assert.equal(dirname(directory),resolve(tmpdir()),'Optimizer temporary directory must stay within the OS temp root');
    rmSync(directory,{recursive:true,force:true});
  }
}
