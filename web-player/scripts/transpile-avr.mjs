import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {dirname,resolve,extname} from 'node:path';
import {parseArgs} from 'node:util';
import {createHash} from 'node:crypto';
import {AVRCore as Runtime} from '../lib/avr-wasm.js';
import {runtimeABI,transpileAVR} from '../lib/avr-transpiler.js';
import {parseHex} from '../lib/hex.js';

const {values,positionals}=parseArgs({allowPositionals:true,options:{'no-flag-dce':{type:'boolean'},help:{type:'boolean'}}});
if(values.help||positionals.length!==2){
  console.log('Usage: node web-player/scripts/transpile-avr.mjs input.hex|input.bin output.wasm [--no-flag-dce]');
  console.log('Target: ATtiny13A. Output imports the existing AVR peripheral WASM runtime.');
  if(!values.help)process.exitCode=1;
}else{
  const [input,output]=positionals.map(p=>resolve(p));
  if(input===output||extname(output).toLowerCase()!=='.wasm')throw new Error('Use a separate .wasm output path');
  const source=readFileSync(input),flash=extname(input).toLowerCase()==='.hex'?parseHex(source.toString('utf8')):new Uint8Array(source);
  const runtime=new Runtime(flash);
  const generated=transpileAVR(flash,runtimeABI(runtime._exports),{optimizeFlags:!values['no-flag-dce']});
  if(!WebAssembly.validate(generated.bytes))throw new Error('Generated WebAssembly failed validation');
  const hash=data=>createHash('sha256').update(data).digest('hex');
  const report={...generated.manifest,sourceSha256:hash(source),flashSha256:hash(flash),wasmSha256:hash(generated.bytes),wasmBytes:generated.bytes.length,
    runtimeSha256:hash(readFileSync(new URL('../wasm/avr.wasm',import.meta.url)))};
  mkdirSync(dirname(output),{recursive:true});
  writeFileSync(output,generated.bytes);writeFileSync(output+'.json',JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({output,bytes:generated.bytes.length,...report.stats},null,2));
}
