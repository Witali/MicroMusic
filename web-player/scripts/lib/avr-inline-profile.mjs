// Validated project-only inline candidates; no raw names, paths or native PCs.
const check=(ok,message)=>{if(!ok)throw Error(message);};
const safe=n=>Number.isSafeInteger(n)&&n>=0;
const keys=(object,allowed)=>check(object&&typeof object==='object'&&!Array.isArray(object)&&
  Object.keys(object).every(key=>allowed.includes(key)),'Invalid inline object fields');
const coordinate=entry=>{
  keys(entry,['source','line']);
  check(typeof entry.source==='string'&&/^web-player\/native\/[A-Za-z0-9_.\/-]+$/.test(entry.source)&&
    !entry.source.split('/').some(p=>!p||p==='.'||p==='..')&&safe(entry.line)&&entry.line>0,'Invalid inline source coordinate');
};
export function prepareInlineContexts(input){
  keys(input,['schema','contexts','frames']);
  check(input.schema==='micromusic-dwarf-inline-contexts-v1'&&Array.isArray(input.contexts),'Invalid inline dictionary');
  check(input.frames&&typeof input.frames==='object'&&!Array.isArray(input.frames),'Invalid inline frame table');
  const frames=new Map();
  for(const [key,value]of Object.entries(input.frames)){
    check(/^(?:0|[1-9]\d*)$/.test(key)&&safe(Number(key)),'Invalid inline frame ID');
    check(value&&['project','support','unresolved'].includes(value.kind),'Invalid inline frame kind');
    keys(value,value.kind==='project'?['kind','function','source','line','callsite']:['kind','callsite']);
    if(value.callsite!==undefined)coordinate(value.callsite);
    if(value.kind==='project'){
      coordinate({source:value.source,line:value.line});
      check(typeof value.function==='string'&&/^[A-Za-z_][A-Za-z_0-9]*$/.test(value.function),'Invalid inline function');
    }
    frames.set(Number(key),value.kind==='project'?{kind:'project',source:value.source,function:value.function,line:value.line}:{kind:value.kind});
  }
  const contexts=input.contexts.map((context,id)=>{
    keys(context,['kind','chains']);
    check(['unique','ambiguous','unresolved'].includes(context.kind)&&Array.isArray(context.chains),'Invalid inline context');
    check(context.kind==='unique'?context.chains.length===1:context.kind==='unresolved'?
      context.chains.length===0:context.chains.length>1,'Inconsistent inline context kind');
    const chains=context.chains;
    for(const chain of chains)check(Array.isArray(chain)&&chain.length>0&&new Set(chain).size===chain.length&&
      chain.every(n=>safe(n)&&frames.has(n)),'Invalid inline scope chain');
    for(let n=0;n<chains.length;n++)for(let m=0;m<chains.length;m++)if(n!==m)
      check(!chains[n].every((v,i)=>chains[m][i]===v),'Duplicate or ancestor inline candidates');
    const leaf=context.kind==='unique'?frames.get(chains[0].at(-1)):null;
    return {id,kind:context.kind,category:leaf?.kind??context.kind,...(leaf?.kind==='project'?{project:leaf}:{})};
  });
  return {contexts,fromName(name){
    const match=/^micromusic-inline-(0|[1-9]\d*)$/.exec(name);
    check(match&&safe(Number(match[1]))&&Number(match[1])<contexts.length,'Invalid inline context label');
    return contexts[Number(match[1])];
  }};
}

export function inlineView(){
  return {budget:{project:0,support:0,ambiguous:0,unresolved:0,unlabelled:0,other:0},
    contexts:new Map(),functions:new Map(),reasons:new Map()};
}
export function recordInline(target,result){
  if(result.category==='other'){target.budget.other++;return;}
  const context=result.inlineContext;
  if(!context){
    target.budget.unlabelled++;
    const reason=result.reason||'absent-inline-label';target.reasons.set(reason,(target.reasons.get(reason)||0)+1);return;
  }
  target.budget[context.category]++;
  if(!target.contexts.has(context.id))target.contexts.set(context.id,{id:context.id,kind:context.kind,ticks:0});
  target.contexts.get(context.id).ticks++;
  if(context.project){
    const {source,function:fn,line}=context.project,key=JSON.stringify([source,fn,line]);
    if(!target.functions.has(key))target.functions.set(key,{source,function:fn,line,ticks:0});
    target.functions.get(key).ticks++;
  }
}
export function finishInline(target,ticks){
  const contexts=[...target.contexts.values()].sort((a,b)=>a.id-b.id),functions=[...target.functions.values()]
    .sort((a,b)=>a.source.localeCompare(b.source)||a.function.localeCompare(b.function)||a.line-b.line);
  check(Object.values(target.budget).reduce((n,v)=>n+v,0)===ticks,'Inline tick budget mismatch');
  check(contexts.reduce((n,c)=>n+c.ticks,0)===ticks-target.budget.other-target.budget.unlabelled,'Inline context budget mismatch');
  check(functions.reduce((n,f)=>n+f.ticks,0)===target.budget.project,'Inline function budget mismatch');
  check([...target.reasons.values()].reduce((n,v)=>n+v,0)===target.budget.unlabelled,'Inline reason budget mismatch');
  return {candidateOnly:true,budget:target.budget,contexts,projectFunctions:functions,
    unlabelledReasons:[...target.reasons].map(([reason,ticks])=>({reason,ticks})).sort((a,b)=>a.reason.localeCompare(b.reason))};
}
