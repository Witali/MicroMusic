// Direct WASM control flow for bounded register-only strongly connected regions.
// AVR words are decoded by the caller, never interpreted by this module at run time.
const controls=new Set(['RJMP','BRANCH','SKIP','CPSE']);
export function planRegions(decoded,{pure,pcMask,width,cycles,maxNodes=64}){
  const nodes=new Map(decoded.filter(i=>pure.has(i.name)||controls.has(i.name)).map(i=>[i.pc,i]));
  const edges=i=>{
    const next=(i.pc+1)&pcMask,target=(next+i.k)&pcMask;
    if(i.name==='RJMP')return[target];
    if(i.name==='BRANCH')return[next,target];
    if(i.name==='SKIP'||i.name==='CPSE')return[next,(next+width(decoded[next].word))&pcMask];
    return[next];
  };
  const index=new Map(),low=new Map(),stack=[],active=new Set(),regions=[];let serial=0;
  function visit(pc){
    index.set(pc,serial);low.set(pc,serial++);stack.push(pc);active.add(pc);
    for(const target of edges(nodes.get(pc)))if(nodes.has(target)){
      if(!index.has(target)){visit(target);low.set(pc,Math.min(low.get(pc),low.get(target)));}
      else if(active.has(target))low.set(pc,Math.min(low.get(pc),index.get(target)));
    }
    if(low.get(pc)!==index.get(pc))return;
    const component=[];let current;
    do{current=stack.pop();active.delete(current);component.push(nodes.get(current));}while(current!==pc);
    if(component.length>maxNodes||component.length===1&&!edges(component[0]).includes(pc))return;
    component.sort((a,b)=>a.pc-b.pc);
    const maxCost=Math.max(...component.map(i=>pure.has(i.name)?cycles(i):i.name==='SKIP'||i.name==='CPSE'?1+width(decoded[(i.pc+1)&pcMask].word):2));
    regions.push({nodes:component,maxCost});
  }
  for(const pc of nodes.keys())if(!index.has(pc))visit(pc);
  return regions.sort((a,b)=>a.nodes[0].pc-b.nodes[0].pc);
}

export function emitRegion(region,{abi,pcMask,width,decoded,pure,cycles,emitALU,readRegister,registers,written,emit:b,state,stateF,put}){
  const {bytes,constant:c,get:g,set:s,call,condition:iff,conditionValue:select,eq,eqz,lt,ge,binary,add,sub,and,
    shr,float,asFloat,load8,store8,loadI64,storeI64,constantI64,store32}=b;
  const PC=11,COUNT=12,CYCLES=13,LIMIT=14,LAST=15,COST=16,cacheBase=18;
  const flagsAddress=c(abi.data+abi.sreg),stop=bytes(c(0),0x0f);
  const bodies=region.nodes.map(i=>{
    const next=(i.pc+1)&pcMask;let code=bytes(s(PC,c(next)),s(COST,c(pure.has(i.name)?cycles(i):1)));
    if(pure.has(i.name))code.push(...emitALU(i));
    else if(i.name==='RJMP')code.push(...s(PC,c((next+i.k)&pcMask)),...s(COST,c(2)));
    else{
      const skip=i.name==='SKIP'||i.name==='CPSE'?width(decoded[next].word):0;
      const test=i.name==='BRANCH'?eq(and(shr(g(7),i.d),c(1)),c(i.s)):
        i.name==='SKIP'?eq(and(shr(readRegister(i.d),i.s),c(1)),c(i.k)):eq(readRegister(i.d),readRegister(i.s));
      code.push(...iff(test,bytes(s(PC,c(i.name==='BRANCH'?(next+i.k)&pcMask:(next+skip)&pcMask)),s(COST,c(i.name==='BRANCH'?2:1+skip)))));
    }
    code.push(...s(LAST,c(i.pc)),...s(CYCLES,add(g(CYCLES),g(COST))),...s(COUNT,add(g(COUNT),c(1))));
    return code;
  });
  const cached=registers(),dirty=written();
  const TIME=cacheBase+cached.length; // One f64 local follows the i32 register cache.
  const bound=binary(0x6c,g(LIMIT),c(region.maxCost)),elapsed=binary(0xa0,stateF('cyc'),asFloat(bound));
  const pending=select(and(load8(flagsAddress),c(128)),call(13),c(0));
  const code=bytes(s(LIMIT,select(lt(g(1),c(32)),g(1),c(32))),
    iff(lt(g(LIMIT),c(2)),stop),iff(state('irqDelay'),stop),iff(pending,stop),
    s(TIME,binary(0xa4,stateF('overflowAt'),float(4503599627370496))),
    s(TIME,binary(0xa4,g(TIME),call(14,g(0)))),
    iff(binary(0x66,elapsed,g(TIME)),bytes(
      iff(binary(0x65,g(TIME),stateF('cyc')),stop),
      // Largest integer budget with budget*maxCost strictly below the span.
      // Enter only when 0 < span <= oldLimit*maxCost (at most 96), so ceil,
      // subtraction/division and trapping i32.trunc_f64_s remain in range.
      s(LIMIT,bytes(binary(0xa3,binary(0xa1,bytes(binary(0xa1,g(TIME),stateF('cyc')),0x9b),float(1)),float(region.maxCost)),0xaa)),
      iff(lt(g(LIMIT),c(2)),stop))),
    iff(binary(0x56,loadI64(c(abi.phase.retired)),binary(0x7d,constantI64(0xffffffffffffffffn),bytes(g(LIMIT),0xad))),stop),
    s(PC,state('pc')),s(7,load8(flagsAddress)),
    ...cached.map((n,index)=>s(cacheBase+index,load8(c(abi.data+n)))));
  // The statically used register union is preloaded once, avoiding a validity
  // branch on every read. Only potentially written registers are committed.
  code.push(0x02,0x40,0x03,0x40,...iff(ge(g(COUNT),g(LIMIT)),[0x0c,2]));
  const indices=new Map(region.nodes.map((i,n)=>[i.pc,n])),first=region.nodes[0].pc,last=region.nodes.at(-1).pc,n=region.nodes.length;
  for(let i=0;i<n;i++)code.push(0x02,0x40);
  code.push(...sub(g(PC),c(first)),0x0e,...b.uleb(last-first+1));
  for(let pc=first;pc<=last;pc++)code.push(...b.uleb(indices.get(pc)??n+1));
  code.push(...b.uleb(n+1));
  bodies.forEach((body,index)=>code.push(0x0b,...body,0x0c,...b.uleb(n-index-1)));
  code.push(0x0b,0x0b,...iff(eqz(g(COUNT)),stop),
    ...store32(c(abi.phase.active),c(1)),...store32(c(abi.phase.execPc),g(LAST)),
    ...store32(c(abi.phase.nextPc),g(PC)),...store32(c(abi.phase.stage),c(0)),
    ...s(2,call(16,asFloat(g(CYCLES)))),...iff(lt(g(2),c(0)),bytes(c(-1),0x0f)),
    ...iff(eqz(g(2)),bytes(put('error',c(25)),c(-1),0x0f)),
    ...dirty.map(n=>store8(c(abi.data+n),g(cacheBase+cached.indexOf(n)))),
    ...store8(flagsAddress,g(7)),...put('pc',g(PC)),...put('errorPC',g(LAST)),
    ...storeI64(c(abi.phase.retired),binary(0x7c,loadI64(c(abi.phase.retired)),binary(0x7d,bytes(g(COUNT),0xad),constantI64(1)))),
    ...call(18),...g(COUNT));
  return {code,locals:16+cached.length,floatLocals:1,registers:cached,written:dirty};
}
