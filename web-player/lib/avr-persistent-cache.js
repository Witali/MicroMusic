import {AVR_CACHE_COMPILER_ID} from './avr-cache-identity.js';
import {createIndexedDBTranslationStore} from './avr-indexeddb-cache.js';
import {DEFAULT_CONFIGURATION,packageConfiguration,validateTranslation,assertPackageRuntimeABI} from './attiny13a-package.js?v=20261026-persistent-cache';
const encoder=new TextEncoder(),defaultStore=createIndexedDBTranslationStore();
const nativeModules=new Map();
const MAX_RECORD_BYTES=16*1024*1024;
const hardwareKeys=Object.keys(DEFAULT_CONFIGURATION);
const executionDefaults={fastIdle:true,fastBlocks:false,optimizeFlags:true,maxBlockInstructions:32,optimizePhaseLocals:false,boundedRegions:false,incrementalCompilation:false};
const supported=new Set([...hardwareKeys,...Object.keys(executionDefaults),'target','cpuHz','cacheTranslation']);
const canonical=value=>value===null||typeof value!=='object'?JSON.stringify(value):Array.isArray(value)
  ?'['+value.map(canonical).join(',')+']':'{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
const sha=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
const policy=manifest=>({optimizeFlags:manifest.optimizeFlags,maxBlockInstructions:manifest.maxBlockInstructions,
  optimizePhaseLocals:manifest.optimizePhaseLocals??false,boundedRegions:manifest.boundedRegions??false});

// Full ATtiny13A only. Persist bytecode, checked using the package validator,
// never a live Instance, Memory, CPU state or changed SPM image.
export async function createCachedDeviceCore({Core,flash,eeprom=null,options={},runtimeBytes,
  store=defaultStore,compilerIdentity=AVR_CACHE_COMPILER_ID}){
  const construct=(opts=options)=>new Core(flash,eeprom,opts);
  const bypass=reason=>{const core=construct();core.persistentTranslationCache={status:'disabled',reason,hit:false,stored:false};return core;};
  if(options.cacheTranslation===false)return bypass('cacheTranslation:false');
  if(!store||!globalThis.crypto?.subtle)return bypass('storage-or-crypto-unavailable');
  if(typeof compilerIdentity!=='string'||!/^[0-9a-f]{64}$/.test(compilerIdentity))return bypass('compiler-identity-unavailable');
  if(Object.keys(options).some(k=>!supported.has(k)))return bypass('custom-runtime-options');
  if(!(flash instanceof Uint8Array)||!flash.length||flash.length>1024||
    (eeprom!==null&&(!(eeprom instanceof Uint8Array)||eeprom.length!==64)))return bypass('invalid-input');
  if(!(runtimeBytes instanceof Uint8Array)||!runtimeBytes.length)return bypass('runtime-bytes-unavailable');
  // Capture all caller inputs before any await. Hash and instantiate exactly the
  // same runtime bytes; a supplied Module identity cannot attest different bytes.
  flash=new Uint8Array(flash);eeprom=eeprom===null?null:new Uint8Array(eeprom);
  options=structuredClone(options);runtimeBytes=new Uint8Array(runtimeBytes);
  const image=new Uint8Array(1024).fill(255);image.set(flash);
  const initialEEPROM=eeprom??new Uint8Array(64).fill(255);
  let configuration;
  try{configuration=packageConfiguration(Object.fromEntries(hardwareKeys.filter(k=>options[k]!==undefined).map(k=>[k,options[k]])));}
  catch{return bypass('invalid-configuration');}
  const execution={...executionDefaults,...Object.fromEntries(Object.keys(executionDefaults).filter(k=>options[k]!==undefined).map(k=>[k,options[k]]))};
  const [runtimeSha256,flashSha256,eepromSha256]=await Promise.all([sha(runtimeBytes),sha(image),sha(initialEEPROM)]);
  if(!nativeModules.has(runtimeSha256)){
    const compiled=WebAssembly.compile(runtimeBytes);nativeModules.set(runtimeSha256,compiled);
    compiled.catch(()=>nativeModules.delete(runtimeSha256));
    while(nativeModules.size>8)nativeModules.delete(nativeModules.keys().next().value);
  }
  const runtimeModule=await nativeModules.get(runtimeSha256);
  const recipe={version:1,device:'ATtiny13A',compilerIdentity,runtimeSha256,flashSha256,eepromSha256,
    target:options.target??'attiny13a',cpuHz:options.cpuHz??9600000,configuration,execution};
  const recipeText=canonical(recipe),key=await sha(encoder.encode(recipeText));
  let status='miss',record;
  try{record=await store.get(key);}catch{status='unavailable';}
  if(record!==null&&record!==undefined){
    try{
      if(!record||typeof record.metadata!=='string'||!(record.bytes instanceof Uint8Array)||
        encoder.encode(record.metadata).length+record.bytes.byteLength>MAX_RECORD_BYTES)throw Error('Invalid AVR cache record');
      const translated=new Uint8Array(record.bytes),metadata=JSON.parse(record.metadata);
      if(metadata.schema!=='micromusic-avr-cache-v2'||canonical(metadata.recipe)!==recipeText)throw Error('Stale AVR cache recipe');
      if(await sha(translated)!==metadata.wasmSha256)throw Error('AVR cache bytecode hash mismatch');
      const manifest=await validateTranslation({flash:image,configuration,runtime:runtimeBytes,translated});
      if(canonical(policy(manifest))!==canonical(policy(execution)))throw Error('AVR cache input/policy mismatch');
      const core=construct({...options,runtimeModule,
        precompiled:{bytes:translated,manifest},
        validateRuntimeABI:abi=>assertPackageRuntimeABI({configuration,abi:{layout:manifest.abi}},abi)});
      core.persistentTranslationCache={status:'hit',key,hit:true,stored:true};return core;
    }catch{
      status='repaired';try{await store.delete(key);}catch{}
    }
  }
  // Constructor/firmware errors propagate normally; storage failure must not
  // turn a supported program into an error or hide a real configuration fault.
  const core=construct({...options,runtimeModule});let stored=false;
  if(status!=='unavailable')try{
    await validateTranslation({flash:image,configuration,runtime:runtimeBytes,
      translated:core.transpiledBytes,manifest:core.transpilation});
    const bytes=new Uint8Array(core.transpiledBytes),metadata=JSON.stringify({schema:'micromusic-avr-cache-v2',recipe,wasmSha256:await sha(bytes)});
    if(encoder.encode(metadata).length+bytes.byteLength<=MAX_RECORD_BYTES)stored=!!await store.put(key,{metadata,bytes});
    if(!stored)status='write-failed';
  }catch{status='write-failed';}
  core.persistentTranslationCache={status,key,hit:false,stored};return core;
}
