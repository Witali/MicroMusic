// Generation-time dataflow annotations, removed before binary serialization.
// No WASM byte decoding or AVR execution is involved.
const kinds=new Set(['avr-local-read','avr-local-write','avr-local-branch']);
const effects=code=>code.flat(Infinity).filter(item=>kinds.has(item?.kind));
export function stripLocalEffects(code){
  return code.flat(Infinity).filter(item=>{
    if(kinds.has(item?.kind))return false;
    if(!Number.isInteger(item)||item<0||item>255)throw Error('Unexpected non-byte in generated WASM');
    return true;
  });
}
export function annotatePhaseLocals(emit){
  const {bytes}=emit;
  const branch=(build,test,yes,no=[])=>bytes(effects(test),
    {kind:'avr-local-branch',yes:effects(yes),no:effects(no)},
    stripLocalEffects(build(test,yes,no)));
  return {
    get:n=>bytes(emit.get(n),{kind:'avr-local-read',local:n}),
    set:(n,value)=>bytes(value,{kind:'avr-local-write',local:n},emit.set(n,[])),
    condition:(test,yes,no=[])=>branch(emit.condition,test,yes,no),
    conditionValue:(test,yes,no)=>branch(emit.conditionValue,test,yes,no),
  };
}
function liveBefore(code,live){
  for(const effect of effects(code).reverse()){
    if(effect.kind==='avr-local-branch')live=liveBefore(effect.yes,live)|liveBefore(effect.no,live);
    else{
      if(!Number.isInteger(effect.local)||effect.local<0||effect.local>9)throw Error('Invalid instruction temporary');
      const bit=1<<effect.local;
      live=effect.kind==='avr-local-read'?live|bit:live&~bit;
    }
  }
  return live;
}
export function phaseLocalMasks(phases,tail){
  let live=liveBefore(tail,0);const masks=new Array(phases.length);
  for(let n=phases.length-1;n>=0;n--){
    // A suspended clock expression is evaluated again on resume, before the
    // later prefix can overwrite any temporary. Retain both dependencies.
    masks[n]=liveBefore(phases[n].clock,live);
    live=liveBefore(phases[n].prefix,masks[n]);
  }
  return masks;
}
