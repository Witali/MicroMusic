import assert from 'node:assert/strict';

// Compiler temporary paths can contain the local account name. The basename
// retains object/source ownership without publishing a personal home directory.
export function profileObjectName(path){
  return path.replaceAll('\\','/').split('/').at(-1);
}
export function profileLinkMap(text){
  return text.replace(/^(\s*-\s+[0-9a-f]+\s+[0-9a-f]+\s+)(.+)(:\([^)]+\))$/gim,
    (_,prefix,path,suffix)=>prefix+profileObjectName(path)+suffix);
}

// The emitter's unoptimized function order. Fail closed if that ABI changes;
// profiler names must never silently attribute a region to an empty fallback.
export function generatedFunctions(core,layout){
  const manifest=core.transpilation,words=manifest.mapping.length,blocks=manifest.blocks;
  const regions=manifest.regions??[],fallbacks=manifest.regionFallbacks??[];
  assert.ok(words>0&&manifest.mapping.every((i,n)=>i.pc===n),'Noncanonical AVR mapping');
  assert.ok(manifest.boundedRegions||(!regions.length&&!fallbacks.length),'Unexpected region metadata');
  const address=pc=>'0x'+(pc*2).toString(16).padStart(4,'0');
  const names=manifest.mapping.map(i=>({name:`cpu.insn_${address(i.pc)}_${i.name||'continuation'}`,role:'instruction'}));
  names.push(...blocks.map(b=>({name:`cpu.block_${address(b.start)}`,role:'basic-block'})));
  names.push(...regions.map((r,n)=>{
    assert.ok(r.pcs.length&&r.pcs.every(pc=>Number.isInteger(pc)&&pc>=0&&pc<words),'Invalid region PCs');
    return {name:`cpu.region_${n}_${address(r.pcs[0])}`,role:'region-body'};
  }));
  names.push(...regions.map((r,n)=>({name:`cpu.region_entry_${n}_${address(r.pcs[0])}`,role:'region-wrapper'})));
  names.push(...fallbacks.map(f=>{
    assert.equal(blocks[f.block]?.start,f.pc,'Invalid fallback block');
    assert.ok(regions[f.region]?.pcs.includes(f.pc),'Invalid fallback region');
    return {name:`cpu.region_fallback_${address(f.pc)}_r${f.region}_b${f.block}`,role:'fallback-wrapper'};
  }));
  names.push({name:'cpu.emptyBlock',role:'empty-block'});
  const drivers=['step','block','run','nextDuty','capturePWM',...(manifest.abi.device?['runUntil','capturePhysical']:[])];
  names.push(...drivers.map(name=>({name:'cpu.'+name,role:'driver'})));
  assert.equal(names.length,layout.bodies.length,'Unexpected generated function count');
  assert.equal(new Set(names.map(f=>f.name)).size,names.length,'Duplicate CPU names');
  const first=layout.imports.length;
  for(const [n,body]of layout.bodies.entries())assert.equal(body.index,first+n,'Noncontiguous CPU functions');
  for(const name of drivers){
    const index=layout.exports.find(e=>e.name===name)?.index;
    assert.equal(names[index-first]?.name,'cpu.'+name,'Generated export/order mismatch: '+name);
  }
  return {layout,functions:layout.bodies.map((body,n)=>({...body,...names[n],category:'generated_cpu_body'}))};
}
