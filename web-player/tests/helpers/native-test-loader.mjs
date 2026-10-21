// Test-process-only injection. Production browser/Node entry points are unchanged.
// Synchronous hooks are preloaded in every node:test child via --import.
// https://nodejs.org/download/release/v22.15.0/docs/api/module.html#customization-hooks
import {registerHooks} from 'node:module';
import {pathToFileURL} from 'node:url';
const target=process.env.MICROMUSIC_AVR_TEST_MODULE;
if(!target)throw new Error('MICROMUSIC_AVR_TEST_MODULE must name the candidate WASM');
const bridgeURL=new URL('../../lib/avr-wasm.js',import.meta.url).href;
const wasmURL=pathToFileURL(target).href;
registerHooks({
  load(url,context,nextLoad){
    const loaded=nextLoad(url,context);
    if(url!==bridgeURL)return loaded;
    const source=typeof loaded.source==='string'?loaded.source:new TextDecoder().decode(loaded.source);
    const anchor="const url = new URL('../wasm/avr.wasm', import.meta.url);";
    if(source.split(anchor).length!==2)throw new Error('Native bridge changed: review candidate test loader');
    return {...loaded,source:source.replace(anchor,'const url = new URL('+JSON.stringify(wasmURL)+');')+
      '\nexport const __testWasmModuleURL = url.href;\n'};
  }
});
