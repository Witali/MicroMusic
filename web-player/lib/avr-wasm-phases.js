// Generation-time clock barriers. Nested WASM control stays inside a phase;
// this module neither decodes AVR instructions nor interprets emitted WASM.
export const clockPhase=expression=>({kind:'avr-clock-phase',expression});
export const isClockPhase=value=>value?.kind==='avr-clock-phase';
export function assertAtomicPhase(...parts){
  if(parts.flat(Infinity).some(isClockPhase))throw Error('A clock barrier must be a top-level instruction phase');
}

export function emitInstructionPhases(marked,{context,pc,clockImport,emit:b}){
  const {bytes,constant,get,set,call,condition,eq,eqz,lt,load32,store32,load64,store64}=b;
  const load=field=>load32(constant(context[field]));
  const store=(field,value)=>store32(constant(context[field]),value);
  const phases=[];let prefix=[];
  for(const item of marked){
    if(isClockPhase(item)){phases.push({prefix,clock:item.expression});prefix=[];}
    else prefix.push(item);
  }
  const save=()=>bytes(...Array.from({length:9},(_,i)=>store32(constant(context.locals+4*i),get(i))),
    store64(constant(context.temp),get(9)));
  const restore=()=>bytes(...Array.from({length:9},(_,i)=>set(i,load32(constant(context.locals+4*i)))),
    set(9,load64(constant(context.temp))));
  const code=bytes(condition(eqz(load('active')),bytes(
    store('active',constant(1)),store('execPc',constant(pc)),store('nextPc',constant(pc+1)),store('stage',constant(0))),restore()));
  phases.forEach((phase,n)=>{
    // Enter executes once, before its possibly partial clock span. Retrying a
    // wait restores locals and enters its wait label without replaying reads,
    // writes, protected commands, or stack operations in the prefix.
    code.push(...condition(eq(load('stage'),constant(2*n)),bytes(phase.prefix,store('stage',constant(2*n+1)))));
    code.push(...condition(eq(load('stage'),constant(2*n+1)),bytes(
      set(10,call(clockImport,phase.clock)),
      condition(lt(get(10),constant(0)),[0x0f]),
      condition(eqz(get(10)),bytes(save(),0x0f)),
      store('stage',constant(2*n+2)))));
  });
  code.push(...condition(eq(load('stage'),constant(2*phases.length)),prefix));
  return code;
}
