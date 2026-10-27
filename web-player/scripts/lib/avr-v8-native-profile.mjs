// Diagnostic data only. Never interpret AVR instructions or publish raw paths/PCs.
const fail=message=>{throw new Error(message);};
const check=(ok,message)=>{if(!ok)fail(message);};
const uint=(value,message)=>{check(typeof value==='string'&&/^\d+$/.test(value),message);const n=Number(value);check(Number.isSafeInteger(n),message);return n;};
const address=(value,message)=>{check(typeof value==='string'&&/^(?:0x)?[0-9a-f]+$/i.test(value),message);const n=BigInt('0x'+value.replace(/^0x/i,''));check(n<=0xffffffffffffffffn,message);return n;};
const safe=n=>Number.isSafeInteger(n)&&n>=0;
const add=(map,key)=>map.set(key,(map.get(key)||0)+1);
const lower=(rows,value,key)=>{let a=0,b=rows.length;while(a<b){const m=(a+b)>>1;if(rows[m][key]<=value)a=m+1;else b=m;}return a?rows[a-1]:null;};

function sourceLabel(source,root=''){
  const raw=(root?root.replace(/\/$/,'')+'/'+source:source).replaceAll('\\','/');
  const anchor='web-player/native/',at=raw.indexOf(anchor);
  if(at<0||(at&&raw[at-1]!=='/'))return null;
  const parts=[];
  for(const part of raw.slice(at+anchor.length).split('/')){
    if(!part||part==='.')continue;
    if(part==='..'){if(!parts.length)return null;parts.pop();}
    else {if(!/^[A-Za-z0-9_.-]+$/.test(part))return null;parts.push(part);}
  }
  return parts.length?anchor+parts.join('/'):null;
}
function decodeMap(map){
  check(map&&map.version===3&&Array.isArray(map.sources)&&map.sources.every(s=>typeof s==='string')&&
    typeof map.mappings==='string'&&!map.mappings.includes(';'),'Invalid single-line source map');
  check(map.names===undefined||(Array.isArray(map.names)&&map.names.every(s=>typeof s==='string')),'Invalid source-map names');
  check(map.sourceRoot===undefined||typeof map.sourceRoot==='string','Invalid source-map root');
  const names=map.names||[],labels=map.sources.map(s=>sourceLabel(s,map.sourceRoot||''));
  const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  let column=0,source=0,line=0,sourceColumn=0,name=0;const rows=[];
  for(const segment of map.mappings?map.mappings.split(','):[]){
    check(segment.length>0,'Empty source-map segment');const values=[];let bits=0,shift=0,pending=false;
    for(const char of segment){const digit=alphabet.indexOf(char);check(digit>=0,'Invalid source-map VLQ');
      bits+=(digit&31)*2**shift;check(Number.isSafeInteger(bits)&&shift<=50,'Source-map VLQ overflow');
      pending=!!(digit&32);if(pending){shift+=5;continue;}
      values.push((bits&1)?-Math.floor(bits/2):Math.floor(bits/2));bits=shift=0;
    }
    check(!pending&&[1,4,5].includes(values.length),'Malformed source-map segment');
    column+=values[0];check(safe(column)&&(!rows.length||column>rows.at(-1).column),'Unordered source-map segment');
    if(values.length===1){rows.push({column,mapped:false});continue;}
    source+=values[1];line+=values[2];sourceColumn+=values[3];
    check(safe(source)&&source<map.sources.length&&safe(line)&&line<Number.MAX_SAFE_INTEGER&&safe(sourceColumn),'Source-map reference out of range');
    if(values.length===5){name+=values[4];check(safe(name)&&name<names.length,'Source-map name out of range');}
    rows.push({column,mapped:true,label:labels[source],line:line+1});
  }
  return {rows,sources:labels.length,projectSources:labels.filter(Boolean).length};
}
function metadata(functions){
  check(Array.isArray(functions),'Function metadata must be an array');const names=new Map(),indices=new Set();
  for(const fn of functions){
    check(fn&&typeof fn.name==='string','Invalid function metadata');if(!fn.name.startsWith('native.'))continue;
    check(/^native\.[A-Za-z0-9_.$]+$/.test(fn.name)&&!names.has(fn.name)&&safe(fn.index)&&!indices.has(fn.index)&&
      safe(fn.codeOffset)&&safe(fn.end)&&fn.end>fn.codeOffset,'Invalid or duplicate native function metadata');
    names.set(fn.name,{name:fn.name,index:fn.index,codeOffset:fn.codeOffset,end:fn.end});indices.add(fn.index);
  }
  return names;
}

// Names are diagnostic custom data. Bind their last function-name table and
// every supplied range to actual, validated body bytes before trusting offsets.
export function validateV8NativeFunctions(functions,wasmBytes){
  check(wasmBytes instanceof Uint8Array&&WebAssembly.validate(wasmBytes),'Invalid native WASM');
  const known=metadata(functions);
  check(known.size===functions.length,'Unexpected native function metadata');
  const decoder=new TextDecoder('utf-8',{fatal:true});
  const reader=(start,end)=>({at:start,end,
    byte(){check(this.at<this.end,'Truncated native WASM');return wasmBytes[this.at++];},
    u32(){let value=0;for(let n=0;n<5;n++){
      const byte=this.byte();check(n<4||(byte&0xf0)===0,'Invalid native WASM integer');value+=(byte&127)*2**(7*n);
      if(!(byte&128))return value;
    }fail('Invalid native WASM integer');},
    string(){const size=this.u32(),end=this.at+size;check(end<=this.end,'Truncated native WASM name');
      let value;try{value=decoder.decode(wasmBytes.subarray(this.at,end));}catch{fail('Invalid native WASM name');}
      this.at=end;return value;},
  });
  const sections=reader(8,wasmBytes.length),bodies=[];let declarations=null,names=null;
  while(sections.at<sections.end){
    const id=sections.byte(),size=sections.u32(),start=sections.at,end=start+size;
    check(end<=sections.end,'Truncated native WASM section');sections.at=end;const r=reader(start,end);
    if(id===2)check(r.u32()===0,'Native WASM imports are unsupported');
    else if(id===3){declarations=r.u32();for(let n=0;n<declarations;n++)r.u32();check(r.at===r.end,'Malformed native function section');}
    else if(id===10){const count=r.u32();for(let index=0;index<count;index++){
      const length=r.u32(),codeOffset=r.at,end=codeOffset+length;
      check(end<=r.end,'Truncated native function body');bodies.push({index,codeOffset,end});r.at=end;
    }check(r.at===r.end,'Malformed native code section');}
    else if(id===0&&r.string()==='name')while(r.at<r.end){
      const kind=r.byte(),length=r.u32(),end=r.at+length;check(end<=r.end,'Truncated native name subsection');
      const sub=reader(r.at,end);r.at=end;
      if(kind===1){const next=new Map(),count=sub.u32();for(let n=0;n<count;n++){
        const index=sub.u32(),name=sub.string();check(!next.has(index),'Duplicate native function name index');next.set(index,name);
      }check(sub.at===sub.end,'Malformed native function names');names=next;}
    }
  }
  check(bodies.length>0&&declarations===bodies.length&&known.size===bodies.length&&names?.size===bodies.length,
    'Incomplete native function metadata');
  for(const body of bodies){const name=names.get(body.index),fn=known.get(name);
    check(fn&&fn.index===body.index&&fn.codeOffset===body.codeOffset&&fn.end===body.end,
      'Native function metadata does not match WASM');
  }
  return {functions:bodies.length,imports:0,bytes:wasmBytes.byteLength};
}
function parseDisassembly(text,known){
  const blocks=[];let block=null,positions=false,instructions=false,total=0;
  const finish=()=>{
    check(block,'Unexpected disassembly end');total++;
    const fn=known.get(block.name);
    if(fn){
      check(block.index===fn.index&&block.compiler&&safe(block.size)&&block.size>0&&block.base!==undefined&&
        block.base+BigInt(block.size)<=0x10000000000000000n,
        'Incomplete or stale native disassembly');
      for(const row of block.positions)check(row.offset<block.size&&row.position<fn.end-fn.codeOffset,
        'Stale native source position');
      blocks.push({...block,fn});
    }
    block=null;positions=instructions=false;
  };
  for(const line of text.split(/\r?\n/)){
    if(line==='--- WebAssembly code ---'){check(!block,'Nested disassembly block');block={positions:[]};continue;}
    if(line==='--- End code ---'){finish();continue;}
    if(!block)continue;
    let m;
    if((m=line.match(/^name: (.*)$/))){check(block.name===undefined,'Duplicate disassembly name');block.name=m[1];}
    else if((m=line.match(/^index: (\d+)$/))){check(block.index===undefined,'Duplicate disassembly index');block.index=uint(m[1],'Invalid disassembly index');}
    else if((m=line.match(/^compiler: (\S+)$/))){check(block.compiler===undefined,'Duplicate disassembly compiler');block.compiler=m[1];}
    else if((m=line.match(/^Instructions \(size = (\d+)\)$/))){check(block.size===undefined,'Duplicate instruction range');block.size=uint(m[1],'Invalid instruction range');instructions=true;}
    else if(instructions&&block.base===undefined&&(m=line.match(/^([0-9a-f]+)\s+([0-9a-f]+)\s+\S+/i))){
      check(address(m[2],'Invalid first instruction offset')===0n,'Missing first native instruction');block.base=address(m[1],'Invalid native base');
    }else if(line==='Source positions:'){check(!block.hasPositions,'Duplicate source-position table');block.hasPositions=true;positions=true;instructions=false;}
    else if(positions&&(m=line.match(/^\s*([0-9a-f]+)\s+(\d+)(?:\s+statement)?\s*$/i))){
      const offset=Number(address(m[1],'Invalid source-position offset')),position=uint(m[2],'Invalid source position');
      check(safe(offset)&&(!block.positions.length||offset>block.positions.at(-1).offset),'Unordered native source positions');
      block.positions.push({offset,position});
    }else if(positions){
      if(!line.trim())positions=false;
      else check(/^\s*pc offset\s+position\s*$/.test(line),'Malformed native source-position row');
    }
  }
  check(!block,'Truncated disassembly block');return {blocks,total};
}

export function auditV8NativeProfile({log,disassembly,functions,sourceMap}){
  check(typeof log==='string'&&typeof disassembly==='string','Profile inputs must be strings');
  const known=metadata(functions),map=sourceMap===null||sourceMap===undefined?null:decodeMap(sourceMap);
  const parsed=parseDisassembly(disassembly,known),generations=[],ticks=[];
  let order=0;
  for(const line of log.split(/\r?\n/)){
    order++;const f=line.split(',');
    check(!['code-move','code-delete'].includes(f[0]),'Unsupported code-address lifecycle record');
    if(f[0]==='code-creation'){
      check(f.length>=7,'Malformed code-creation record');const start=address(f[4],'Invalid code-creation address'),size=uint(f[5],'Invalid code-creation size');
      check(size>0&&start+BigInt(size)<=0x10000000000000000n,'Invalid code-creation range');
      generations.push({start,end:start+BigInt(size),time:uint(f[3],'Invalid creation timestamp'),order,fn:known.get(f[6])||null});
    }else if(f[0]==='tick'){
      check(f.length>=6&&/^[01]$/.test(f[3]),'Malformed tick record');
      ticks.push({pc:address(f[1],'Invalid tick address'),time:uint(f[2],'Invalid tick timestamp'),order,external:f[3]==='1'});
    }
  }
  const budget={project:0,support:0,unresolvedNative:0,other:0},reasons=new Map(),ownership=new Map();
  const unresolved=reason=>{budget.unresolvedNative++;add(reasons,reason);};
  for(const tick of ticks){
    const candidates=generations.filter(g=>g.order<tick.order&&g.time<=tick.time&&tick.pc>=g.start&&tick.pc<g.end);
    if(tick.external){budget.other++;continue;}
    if(!candidates.length||!candidates.some(g=>g.fn)){budget.other++;continue;}
    if(candidates.length!==1){unresolved('ambiguous-address-generation');continue;}
    const g=candidates[0];if(g.time===tick.time){unresolved('creation-time-tie');continue;}
    const matches=parsed.blocks.filter(b=>b.fn===g.fn&&b.base===g.start&&BigInt(b.size)<=g.end-g.start);
    if(matches.length!==1){unresolved(matches.length?'ambiguous-disassembly':'missing-disassembly');continue;}
    const block=matches[0],offset=Number(tick.pc-g.start);
    if(offset>=block.size){unresolved('native-location-gap');continue;}
    const position=lower(block.positions,offset,'offset');
    if(!position){unresolved(block.positions.length?'native-location-gap':'absent-native-positions');continue;}
    if(position.position===0){unresolved('function-entry-position');continue;}
    if(!map){unresolved('absent-source-map');continue;}
    const source=lower(map.rows,g.fn.codeOffset+position.position,'column');
    if(!source||source.column<g.fn.codeOffset){unresolved('source-map-function-gap');continue;}
    if(!source.mapped){unresolved('unmapped-source-map');continue;}
    if(!source.label){budget.support++;continue;}
    budget.project++;const key=source.label+'|'+source.line;
    if(!ownership.has(key))ownership.set(key,{source:source.label,line:source.line,ticks:0});ownership.get(key).ticks++;
  }
  check(Object.values(budget).reduce((a,b)=>a+b,0)===ticks.length,'Tick budget mismatch');
  return {schema:'micromusic-avr-v8-native-profile-v1',exclusiveSubsystemTimeAvailable:false,
    counts:{ticks:ticks.length,codeGenerations:generations.length,knownNativeGenerations:generations.filter(g=>g.fn).length,
      disassemblyBlocks:parsed.total,knownNativeDisassemblyBlocks:parsed.blocks.length,
      sourceMapSegments:map?.rows.length||0,sourceMapSources:map?.sources||0,projectSourceMapSources:map?.projectSources||0},
    budget,unresolvedReasons:[...reasons].map(([reason,ticks])=>({reason,ticks})).sort((a,b)=>a.reason.localeCompare(b.reason)),
    sourceLines:[...ownership.values()].sort((a,b)=>a.source.localeCompare(b.source)||a.line-b.line),
    limits:[
      'Disjoint raw tick leaf-PC observations only; inclusive stack frames are not counted.',
      'Whole-process ticks include construction, warmup and unrelated work; no emulator work-window duration is inferred.',
      'Predecessor native source positions and source-map segments are attribution candidates, not proven exclusive ownership or elapsed durations.',
      'Function-entry positions, unmapped spans, address-generation ties and ambiguous generations remain unresolved.',
      'Source-map lines cannot recover full C inline scopes, optimized-away code or timing between samples; no speed or real-time claim is made.',
    ]};
}
