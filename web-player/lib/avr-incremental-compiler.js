// Construction-time linker for the trusted AVR emitter, not an arbitrary WASM
// package rewriter. Hot dispatch and all cross-module calls remain inside WASM.
const flat=(...parts)=>parts.flat(Infinity);
const uleb=n=>{const out=[];do{const b=n&127;n>>>=7;out.push(b|(n?128:0));}while(n);return out;};
const vector=items=>flat(uleb(items.length),items);
const string=s=>{const b=Array.from(new TextEncoder().encode(s));return flat(uleb(b.length),b);};
const section=(id,data)=>flat(id,uleb(data.length),data);
const header=[0,97,115,109,1,0,0,0];
const globals=[['controlRequest',0x7f],['watchdogResetCycle',0x7c],['debugEnabled',0x7f],['captureFault',0x7f]];
const equal=(a,b)=>a.length===b.length&&a.every((v,i)=>v===b[i]);
// Keep the initial monolithic runner and its table. Extra private exports make
// its original functions usable as seeds without compiling thirty-two modules.
function seedBytes(bytes,units,firstFunction){
  let p=8;const unsigned=()=>{let n=0;for(let shift=0;shift<35;shift+=7){const b=bytes[p++];n+=(b&127)*2**shift;if(!(b&128))return n;}throw Error('Invalid seed section');};
  while(p<bytes.length){
    const start=p,id=bytes[p++],size=unsigned(),end=p+size;
    if(id===7){
      const count=unsigned(),extra=[flat(string('cpuTable'),1,0),...units.flatMap((u,n)=>
        u.tier!==2||u.id==='emptyBlock'?[flat(string(u.id),0,uleb(firstFunction+n))]:[])];
      return Uint8Array.from(flat(Array.from(bytes.subarray(0,start)),section(7,flat(uleb(count+extra.length),
        Array.from(bytes.subarray(p,end)),extra)),Array.from(bytes.subarray(end))));
    }
    p=end;
  }
  throw Error('Missing seed exports');
}

// Walk exactly the MVP opcodes produced by avr-transpiler.js. Refuse unknown
// opcodes rather than treating instruction operands as function references.
function rewriteCalls(body,map){
  let p=0;const read=()=>{if(p>=body.length)throw Error('Truncated incremental function');return body[p++];};
  const unsigned=()=>{let n=0;for(let shift=0;shift<35;shift+=7){const b=read();n+=(b&127)*2**shift;if(!(b&128))return n;}throw Error('Invalid incremental index');};
  const signed=()=>{for(let n=0;n<10;n++)if(!(read()&128))return;throw Error('Invalid incremental constant');};
  const size=unsigned();if(size!==body.length-p)throw Error('Invalid incremental body size');
  const start=p,count=unsigned();for(let n=0;n<count;n++){unsigned();read();}
  const out=Array.from(body.slice(start,p));
  while(p<body.length){
    const from=p,op=read();
    if(op===0x10){const index=unsigned();out.push(op,...uleb(map(index)));continue;}
    if(op===2||op===3||op===4||op===0x41||op===0x42)signed();
    else if(op===0x0c||op===0x0d||op>=0x20&&op<=0x24||op===0x3f||op===0x40)unsigned();
    else if(op===0x0e){const n=unsigned();for(let i=0;i<=n;i++)unsigned();}
    else if(op===0x11){unsigned();unsigned();}
    else if(op>=0x28&&op<=0x3e){unsigned();unsigned();}
    else if(op===0x43||op===0x44){for(let i=0;i<(op===0x43?4:8);i++)read();}
    else if(![0,1,5,0x0b,0x0f,0x1a,0x1b].includes(op)&&!(op>=0x45&&op<=0xc4))
      throw Error('Unsupported incremental opcode: '+op.toString(16));
    out.push(...body.slice(from,p));
  }
  return flat(uleb(out.length),out);
}

export function compileIncremental(linkage,previous){
  const {types,imports,firstFunction,functionTypes,codes,units,table,flashWords,pageWords,memoryPages}=linkage;
  if(units.length!==codes.length||units.length!==functionTypes.length||table.length!==flashWords*2)
    throw Error('Invalid incremental function layout');
  const byIndex=new Map(units.map((u,n)=>[firstFunction+n,{...u,index:firstFunction+n,type:functionTypes[n],body:codes[n]}]));
  const groups=new Map();
  for(const u of byIndex.values()){
    const id=u.tier===2?'shell':(u.tier?'wrappers/':'page/')+Math.floor(u.pc/pageWords);
    if(!groups.has(id))groups.set(id,{id,tier:u.tier,units:[]});groups.get(id).units.push(u);u.group=id;
  }
  const baseImports=[flat(string('avr'),string('memory'),2,1,uleb(memoryPages),uleb(memoryPages)),
    ...imports.map(([name,type])=>flat(string('avr'),string(name),0,uleb(type)))];
  const shell=groups.get('shell'),compiled=new Map();let compiledCount=0,reusedCount=0;
  const dependencies=g=>{
    const result=new Map();
    for(const u of g.units)rewriteCalls(u.body,index=>{
      if(index>=firstFunction){const target=byIndex.get(index);if(!target)throw Error('Missing incremental callee');
        if(target.group!==g.id)result.set(target.id,target);}
      return index;
    });
    return [...result.values()].sort((a,b)=>a.id.localeCompare(b.id));
  };
  const fresh=!previous||previous.identity!==linkage.identity;
  const seed=fresh?seedBytes(linkage.moduleBytes,units,firstFunction):null,initialModule=seed?new WebAssembly.Module(seed):null;
  for(const g of groups.values()){
    const old=!fresh?previous.groups.get(g.id):null;
    if(initialModule){
      // Base units call only native bridges; wrappers also name generated
      // region/block functions. The emitter owns this split and its tests.
      const deps=g.tier===1?dependencies(g):[];
      const indices=new Map([...deps,...g.units].map((u,n)=>[u.index,firstFunction+n]));
      compiled.set(g.id,{id:g.id,tier:g.tier,module:initialModule,seed:true,bytes:g===shell?seed:null,
        dependencies:deps.map(u=>u.id),exports:g.units.map(u=>u.id),
        canonical:g.tier===1?g.units.map(u=>rewriteCalls(u.body,index=>index<firstFunction?index:indices.get(index))):[],
        sources:g.units.map(u=>({id:u.id,type:u.type,body:u.body}))});
      continue;
    }
    if(g===shell){compiled.set(g.id,previous.shell);reusedCount++;continue;}
    if(old&&g.tier===0&&old.sources.length===g.units.length&&g.units.every((u,n)=>u.id===old.sources[n].id&&u.type===old.sources[n].type&&
      (u.body===old.sources[n].body||equal(u.body,old.sources[n].body)))){
      compiled.set(g.id,old);reusedCount++;continue;
    }
    const deps=dependencies(g);
    if(g===shell&&deps.length)throw Error('Dispatcher must not depend directly on instruction fragments');
    if(g!==shell&&deps.some(u=>u.tier>=g.tier))throw Error('Cyclic incremental dependencies');
    const indices=new Map([...deps,...g.units].map((u,n)=>[u.index,firstFunction+n]));
    const bodies=g.units.map(u=>rewriteCalls(u.body,index=>index<firstFunction?index:indices.get(index)));
    if(old?.seed&&g.tier===1&&old.exports.length===g.units.length&&g.units.every((u,n)=>u.id===old.exports[n])&&
      old.dependencies.length===deps.length&&deps.every((u,n)=>u.id===old.dependencies[n]&&compiled.get(u.group)?.module===previous.groups.get(u.group)?.module)&&
      bodies.every((b,n)=>equal(b,old.canonical[n]))){compiled.set(g.id,old);reusedCount++;continue;}
    const importsHere=[...baseImports,...(g===shell?[]:globals.map(([name,type])=>flat(string('cpu'),string(name),3,type,1))),
      ...deps.map(u=>flat(string('code'),string(u.id),0,uleb(u.type)))];
    const exportsHere=g.units.map(u=>flat(string(u.id),0,uleb(indices.get(u.index))));
    if(g===shell)exportsHere.push(...globals.map(([name],n)=>flat(string(name),3,n)),flat(string('cpuTable'),1,0));
    const globalSection=g===shell?section(6,vector(globals.map(([,type],n)=>type===0x7f?[0x7f,1,0x41,0,0x0b]:
      [0x7c,1,0x44,0,0,0,0,0,0,0xf0,0xbf,0x0b]))):[];
    const bytes=Uint8Array.from(flat(header,section(1,vector(types)),section(2,vector(importsHere)),
      section(3,vector(g.units.map(u=>uleb(u.type)))),
      g===shell?section(4,[1,0x70,1,...uleb(flashWords*2),...uleb(flashWords*2)]):[],globalSection,
      section(7,vector(exportsHere)),section(10,vector(bodies))));
    const module=old?.bytes&&equal(old.bytes,bytes)?old.module:new WebAssembly.Module(bytes);
    if(module===old?.module)reusedCount++;else compiledCount++;
    compiled.set(g.id,{id:g.id,tier:g.tier,bytes,module,dependencies:deps.map(u=>u.id),exports:g.units.map(u=>u.id),
      sources:g.units.map(u=>({id:u.id,type:u.type,body:u.body}))});
  }
  const plan={groups:compiled,table:table.map(index=>byIndex.get(index).id),
    shell:compiled.get('shell'),identity:linkage.identity,
    byteLength:[...compiled.values()].reduce((n,g)=>n+(g.bytes?.length??0)+(g.canonical??[]).reduce((s,b)=>s+b.length,0),0),compiledCount:fresh?1:compiledCount,reusedCount};
  return {module:plan.shell.module,incremental:plan};
}

export function instantiateIncremental(plan,avr,previous){
  const sameShell=previous?.module===plan.shell.module;
  const shell=sameShell?previous.shell:new WebAssembly.Instance(plan.shell.module,{avr}).exports;
  const functions=new Map(Object.entries(shell).filter(([,fn])=>typeof fn==='function')),instances=new Map();let instantiated=0,reused=0,seededGroups=0;
  for(const group of [...plan.groups.values()].filter(g=>g.id!=='shell').sort((a,b)=>a.tier-b.tier||a.id.localeCompare(b.id))){
    const deps=group.dependencies.map(name=>functions.get(name));
    if(deps.some(fn=>typeof fn!=='function'))throw Error('Unbound incremental function');
    const old=previous?.instances.get(group.id);
    const reuse=sameShell&&old?.module===group.module&&deps.every((fn,i)=>old.dependencies[i]===fn);
    const exports=reuse?old.exports:group.seed?Object.fromEntries(group.exports.map(name=>[name,shell[name]])):new WebAssembly.Instance(group.module,{avr,cpu:shell,
      code:Object.fromEntries(group.dependencies.map((name,n)=>[name,deps[n]]))}).exports;
    if(group.seed)seededGroups++;
    if(reuse)reused++;else if(!group.seed)instantiated++;
    instances.set(group.id,{module:group.module,dependencies:deps,exports});
    for(const name of group.exports)functions.set(name,exports[name]);
  }
  // Validate every binding before mutating the live dispatcher. No chip runs
  // during synchronous linking; a compile/link failure leaves its old table.
  const entries=plan.table.map(id=>functions.get(id));
  if(entries.some(fn=>typeof fn!=='function'))throw Error('Incomplete incremental dispatch table');
  let changedSlots=0;
  entries.forEach((fn,n)=>{if(shell.cpuTable.get(n)!==fn){shell.cpuTable.set(n,fn);changedSlots++;}});
  for(const [name] of globals)shell[name].value=name==='watchdogResetCycle'?-1:0;
  const publicExports=Object.fromEntries([...globals.map(([name])=>name),'cpuTable','step','block','run','nextDuty','capturePWM','runUntil','capturePhysical']
    .map(name=>[name,shell[name]]));
  return {exports:publicExports,module:plan.shell.module,shell,instances,
    diagnostics:{groups:plan.groups.size,instantiated,reusedInstances:reused,seededGroups,changedSlots}};
}
