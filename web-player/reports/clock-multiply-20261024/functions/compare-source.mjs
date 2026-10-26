// Static diagnostics only: rebuild exact artifacts in a unique ignored folder.
// No runtime workload, sampling, timing experiment or production write occurs.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {execFileSync,spawnSync} from 'node:child_process';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync,existsSync} from 'node:fs';
import {dirname,join,parse,resolve,relative,isAbsolute} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{'baseline-ref':{type:'string',default:'4f09550'},
  'candidate-ref':{type:'string',default:'working-tree'},'out-dir':{type:'string',default:'build/function-comparisons'},
  'reuse-dir':{type:'string'},'self-test':{type:'boolean'},profile:{type:'string',multiple:true},emsdk:{type:'string'},help:{type:'boolean'}}});
if(values.help){
  console.log('node web-player/scripts/compare-device-functions.mjs [--baseline-ref 4f09550] [--candidate-ref working-tree|commit] [--out-dir build/function-comparisons] [--reuse-dir build/function-comparisons/compare-ID] [--profile path/to/summary.json] [--emsdk path] [--self-test]');
  process.exit(0);
}
const hash=value=>createHash('sha256').update(value).digest('hex');
const normalized=value=>value.toString('utf8').replaceAll('\r\n','\n');
const git=args=>execFileSync('git',args,{cwd:root,maxBuffer:32*1024*1024});
const text=args=>git(args).toString().trim();
const save=(file,value)=>writeFileSync(file,JSON.stringify(value,null,2)+'\n');
const beneath=(parent,path)=>{const rel=relative(parent,path);return rel!==''&&!isAbsolute(rel)&&rel!=='..'&&!rel.startsWith('..'+(process.platform==='win32'?'\\':'/'));};
let out,sdk,tools;
function run(executable,args,cwd=root){
  const result=spawnSync(executable,args,{cwd,encoding:'utf8',maxBuffer:64*1024*1024});
  if(result.error)throw result.error;
  assert.equal(result.status,0,`${executable}: ${result.stderr}`);return result;
}

class Reader{
  constructor(data,start=0,end=data.length){this.data=data;this.at=start;this.end=end;}
  u8(){assert.ok(this.at<this.end,'truncated WASM');return this.data[this.at++];}
  u32(){let n=0,shift=0,b;do{b=this.u8();n+=(b&127)*2**shift;shift+=7;assert.ok(shift<=35);}while(b&128);return n;}
  string(){const size=this.u32(),at=this.at;this.at+=size;assert.ok(this.at<=this.end);return this.data.subarray(at,this.at).toString('utf8');}
}
function sections(binary){
  assert.ok(binary.subarray(0,8).equals(Buffer.from([0,97,115,109,1,0,0,0])));
  const r=new Reader(binary,8),result=[];
  while(r.at<r.end){const start=r.at,id=r.u8(),size=r.u32(),payload=r.at;r.at+=size;assert.ok(r.at<=r.end);result.push({id,start,payload,end:r.at});}
  return result;
}
function layout(binary){
  const bodies=[],exports=[];
  for(const s of sections(binary)){
    const r=new Reader(binary,s.payload,s.end);
    if(s.id===2)assert.equal(r.u32(),0,'native artifact must have no imports');
    if(s.id===7)for(let n=r.u32();n;n--){const name=r.string(),kind=r.u8(),index=r.u32();if(kind===0)exports.push({name,index});}
    if(s.id===10){for(let n=r.u32(),index=0;n;n--,index++){
      const size=r.u32(),start=r.at;r.at+=size;assert.ok(r.at<=r.end);bodies.push({index,start,end:r.at,size,rawSha256:hash(binary.subarray(start,r.at))});
    }assert.equal(r.at,r.end);}
  }
  return {bodies,exports};
}
const executable=binary=>Buffer.concat([binary.subarray(0,8),...sections(binary).filter(s=>s.id!==0).map(s=>binary.subarray(s.start,s.end))]);
const leb=n=>{const result=[];do{let b=n&127;n=Math.floor(n/128);result.push(b|(n?128:0));}while(n);return result;};
const str=s=>{const b=Buffer.from(s);return [...leb(b.length),...b];};
function named(binary,names){
  const entries=[...leb(names.size),...[...names].flatMap(([index,name])=>[...leb(index),...str('native.'+name)])];
  const payload=Buffer.from([...str('name'),1,...leb(entries.length),...entries]);
  const result=Buffer.concat([binary,Buffer.from([0,...leb(payload.length)]),payload]);
  assert.ok(executable(result).equals(executable(binary)),'diagnostic names changed executable sections');return result;
}

// A small S-expression reader preserves original WAT spans and exact atom
// values. It handles escaped strings, line comments and nested block comments.
function watTree(source){
  let at=0;
  function space(){for(;;){
    while(/\s/.test(source[at]??'')&&at<source.length)at++;
    if(source.startsWith(';;',at)){const end=source.indexOf('\n',at);at=end<0?source.length:end+1;continue;}
    if(source.startsWith('(;',at)){at+=2;let depth=1;while(depth){assert.ok(at<source.length,'unterminated WAT comment');if(source.startsWith('(;',at)){depth++;at+=2;}else if(source.startsWith(';)',at)){depth--;at+=2;}else at++;}continue;}
    break;
  }}
  function node(){space();const start=at;
    if(source[at]==='('){at++;const children=[];for(;;){space();assert.ok(at<source.length,'unterminated WAT list');if(source[at]===')'){at++;return {start,end:at,children};}children.push(node());}}
    if(source[at]==='"'){at++;while(at<source.length){const ch=source[at++];if(ch==='\\')at++;else if(ch==='"')return {start,end:at,value:source.slice(start,at)};}throw Error('unterminated WAT string');}
    while(at<source.length&&!/[\s()]/.test(source[at]))at++;
    assert.ok(at>start,'invalid WAT atom');return {start,end:at,value:source.slice(start,at)};
  }
  const tree=node();space();assert.equal(at,source.length);assert.equal(tree.children[0].value,'module');return tree;
}
const atoms=node=>node.children?node.children.flatMap(atoms):[node];
const canonicalNode=(node,replacement=token=>token.value)=>node.children?
  '('+node.children.map(child=>canonicalNode(child,replacement)).join(' ')+')':replacement(node);
function decodedFunctions(wat,names){
  const tree=watTree(wat),types=new Map(),functions=new Map();
  for(const child of tree.children.slice(1))if(child.children?.[0].value==='type'){
    const [kind,name,...definition]=child.children;assert.ok(name.value.startsWith('$'));
    // C builds use only structural function signatures; reject recursive/GC
    // reference types instead of silently treating their names as equivalent.
    const tokens=definition.flatMap(atoms).map(v=>v.value);
    assert.ok(!tokens.some(v=>v.startsWith('$')),'type references require a stronger canonicalizer');
    types.set(name.value,'$signature_'+hash(definition.map(node=>canonicalNode(node)).join(' ')));
    assert.equal(kind.value,'type');
  }
  for(const child of tree.children.slice(1))if(child.children?.[0].value==='func'){
    const list=atoms(child),name=list[1].value;
    assert.ok(name.startsWith('$native.'),'disassembler did not retain explicit function names');
    const symbol=name.slice('$native.'.length);assert.ok([...names.values()].includes(symbol));
    // WAT type identifiers and local/label identifiers have independent
    // namespaces. Replace only the actual type-use token objects, never every
    // atom whose spelling happens to match a type identifier such as $0.
    const typeUses=new Map();
    function visit(node){if(!node.children)return;
      if(node.children[0].value==='type'){
        assert.equal(node.children.length,2,'unsupported type use');
        const token=node.children[1];assert.ok(types.has(token.value),'unknown type use');
        typeUses.set(token,types.get(token.value));
      }
      node.children.forEach(visit);
    }
    visit(child);
    const replacement=token=>typeUses.get(token)??token.value;
    const canonical=canonicalNode(child,replacement);
    let display='',cursor=child.start;
    for(const token of list){display+=wat.slice(cursor,token.start)+replacement(token);cursor=token.end;}
    display+=wat.slice(cursor,child.end)+'\n';
    assert.ok(!functions.has(symbol),'duplicate function symbol '+symbol);
    functions.set(symbol,{normalizedSha256:hash(canonical),normalizedWat:display,originalWat:wat.slice(child.start,child.end)+'\n'});
  }
  assert.equal(functions.size,names.size);return {functions,types:Object.fromEntries(types)};
}

function checkCanonicalizer(){
  const names=new Map([[0,'identity']]);
  const fixture=type=>`(module
    (type $0 (func (param ${type?'i64':'i32'}) (result ${type?'i64':'i32'})))
    (type $1 (func (param ${type?'i32':'i64'}) (result ${type?'i32':'i64'})))
    (table 1 funcref)
    (func $native.identity (param $0 i32) (result i32)
      (block $1 (result i32)
        (call_indirect (type $${type}) (local.get $0) (i32.const 0)))))`;
  const decode=wat=>decodedFunctions(wat,names).functions.get('identity');
  const a=decode(fixture(0)),b=decode(fixture(1));
  assert.equal(a.normalizedSha256,b.normalizedSha256,'type renumbering must normalize independently of local/label spellings');
  for(const result of [a,b]){
    assert.match(result.normalizedWat,/\(param \$0 i32\)/);
    assert.match(result.normalizedWat,/\(local.get \$0\)/);
    assert.match(result.normalizedWat,/\(block \$1/);
    assert.match(result.normalizedWat,/\(type \$signature_[0-9a-f]{64}\)/);
  }
  assert.notEqual(a.normalizedSha256,decode(fixture(0).replace('(local.get $0)','(i32.const 7)')).normalizedSha256,'operand changes must remain visible');
  assert.notEqual(a.normalizedSha256,decode(fixture(0).replace('(type $0) (local.get','(type $1) (local.get')).normalizedSha256,'a different structural type must remain visible');
  assert.notEqual(canonicalNode(watTree('(module (block (drop (i32.const 1))))')),
    canonicalNode(watTree('(module (block (drop) (i32.const 1)))')),'S-expression nesting must remain visible');
  return {typeLocalLabelCollision:true,typeIndexPermutation:true,changedOperand:true,changedType:true,preservedNesting:true};
}
const canonicalizerChecks=checkCanonicalizer();
if(values['self-test']){console.log(JSON.stringify({canonicalizerChecks}));process.exit(0);}

const parent=resolve(root,values['out-dir']);
assert.ok(beneath(resolve(root,'build'),parent),'output parent must be below this checkout/build');
assert.equal(spawnSync('git',['check-ignore','--quiet',relative(root,join(parent,'probe'))],{cwd:root}).status,0,'output must be Git-ignored');
if(values['reuse-dir']){
  out=resolve(root,values['reuse-dir']);assert.ok(beneath(resolve(root,'build'),out),'reuse directory must be below checkout/build');
  assert.equal(spawnSync('git',['check-ignore','--quiet',relative(root,join(out,'probe'))],{cwd:root}).status,0);
  tools=JSON.parse(readFileSync(join(out,'summary.json'))).tools;
}else{
  mkdirSync(parent,{recursive:true});out=mkdtempSync(join(parent,'compare-'));
  sdk=values.emsdk||process.env.EMSDK;
  for(let at=root;!sdk;at=dirname(at)){
    const candidate=join(at,'build/toolchains/emscripten-6.0.12');
    if(existsSync(join(candidate,'upstream/bin',process.platform==='win32'?'clang.exe':'clang')))sdk=candidate;
    if(at===parse(at).root)break;
  }
  assert.ok(sdk,'Pass --emsdk for the exact prepared SDK');sdk=resolve(sdk);
  tools=Object.fromEntries(['clang','wasm-opt','wasm-dis'].map(name=>{
    const path=join(sdk,'upstream/bin',name+(process.platform==='win32'?'.exe':''));
    return[name,{path,sha256:hash(readFileSync(path)),version:run(path,['--version']).stdout.trim()}];
  }));
}
// Text provenance follows the same normalized-LF contract as native manifest
// inputs, so a Git autocrlf checkout preserves the source/snapshot proof.
const scriptSource=normalized(readFileSync(fileURLToPath(import.meta.url)));
const scriptSha256=hash(scriptSource);
writeFileSync(join(out,'compare-source.mjs'),scriptSource);

const nativePath='web-player/wasm/attiny13a.wasm',manifestPath='web-player/wasm/device-build.json';
const workingGuard=new Map([nativePath,manifestPath].map(path=>[path,hash(readFileSync(resolve(root,path)))]));
function functionMap(folder){return new Map(readFileSync(join(folder,'runtime-optimized.map'),'utf8').split(/\r?\n/).filter(line=>/^\d+:/.test(line)).map(line=>{
  const colon=line.indexOf(':');return [Number(line.slice(0,colon)),line.slice(colon+1)];
}));}
function inventory(folder,binary,names){
  assert.equal(new Set(names.values()).size,names.size,'duplicate optimized symbol');
  const shape=layout(binary);assert.equal(names.size,shape.bodies.length);
  for(const fn of shape.exports)assert.equal(names.get(fn.index),fn.name,'export/symbol mismatch');
  const wat=readFileSync(join(folder,'runtime.wat'),'utf8'),decoded=decodedFunctions(wat,names);
  const functions=new Map(shape.bodies.map(body=>{const symbol=names.get(body.index);return[symbol,{symbol,...body,...decoded.functions.get(symbol)}];}));
  save(join(folder,'functions.json'),[...functions.values()].map(({normalizedWat,originalWat,...body})=>body));
  return {functions,types:decoded.types,watSha256:hash(wat)};
}
function rebuild(id,ref){
  const work=ref==='working-tree',commit=text(['rev-parse',work?'HEAD':ref]);
  const load=path=>work?readFileSync(resolve(root,path)):git(['show',`${commit}:${path}`]);
  const binary=load(nativePath),manifest=JSON.parse(load(manifestPath));
  assert.equal(hash(binary),manifest.artifacts['attiny13a.wasm']);assert.equal(binary.length,manifest.bytes);
  if(values['reuse-dir']){
    const folder=join(out,id),provenance=JSON.parse(readFileSync(join(folder,'provenance.json')));
    assert.deepEqual(JSON.parse(readFileSync(join(folder,'device-build.json'))),manifest,'reused manifest differs from requested revision');
    assert.equal(provenance.runtimeSha256,hash(binary));assert.ok(provenance.rebuildByteEqual);
    assert.ok(readFileSync(join(folder,'runtime-original.wasm')).equals(binary));
    assert.ok(readFileSync(join(folder,'runtime-rebuilt.wasm')).equals(binary),'reused exact rebuild differs');
    const decorated=readFileSync(join(folder,'runtime-named.wasm'));
    assert.equal(hash(decorated),provenance.namedRuntimeSha256);assert.ok(executable(decorated).equals(executable(binary)));
    const disassembler=tools['wasm-dis'];assert.equal(hash(readFileSync(disassembler.path)),disassembler.sha256);
    console.log('Reuse exact rebuild and disassemble '+id+' '+commit);
    run(disassembler.path,[join(folder,'runtime-named.wasm'),'-o',join(folder,'runtime.wat')]);
    const decoded=inventory(folder,binary,functionMap(folder));
    if(provenance.watSha256)assert.equal(decoded.watSha256,provenance.watSha256,'reused disassembly differs');
    const reused={...provenance,watSha256:decoded.watSha256,types:decoded.types,reusedWithoutBuild:true,
      reuseRequest:{ref,commit}};
    save(join(folder,'provenance.json'),reused);return {provenance:reused,functions:decoded.functions};
  }
  assert.equal(tools.clang.version.split(/\r?\n/)[0],manifest.compilerVersion,'compiler version mismatch');
  const folder=join(out,id),inputs=join(folder,'source');mkdirSync(inputs,{recursive:true});
  for(const [path,expected] of Object.entries(manifest.inputs)){
    const content=normalized(load(path));assert.equal(hash(content),expected,id+'/'+path);
    const target=resolve(inputs,path);assert.ok(beneath(inputs,target));mkdirSync(dirname(target),{recursive:true});writeFileSync(target,content);
    if(work)workingGuard.set(path,hash(readFileSync(resolve(root,path))));
  }
  save(join(folder,'device-build.json'),manifest);writeFileSync(join(folder,'runtime-original.wasm'),binary);
  const pre=join(folder,'runtime-preopt.wasm'),optimized=join(folder,'runtime-rebuilt.wasm'),link=join(folder,'runtime-link.map');
  const compileArgs=[...manifest.flags.map(flag=>flag.replaceAll('<emsdk>',sdk)),'--no-wasm-opt',`-Wl,-Map=${link}`,
    ...manifest.sources,'-lc','-lclang_rt.builtins','-o',pre];
  console.log('Static rebuild '+id+' '+commit);const compiled=run(tools.clang.path,compileArgs,inputs);
  writeFileSync(join(folder,'compiler.stderr.txt'),compiled.stderr);
  const optimizeArgs=[pre,'-O3','--print-function-map','-o',optimized],opt=run(tools['wasm-opt'].path,optimizeArgs,inputs);
  writeFileSync(join(folder,'runtime-optimized.map'),opt.stdout);writeFileSync(join(folder,'optimizer.stderr.txt'),opt.stderr);
  assert.ok(readFileSync(optimized).equals(binary),id+' rebuild must equal every production byte');
  const names=functionMap(folder);
  const decorated=named(binary,names),namedPath=join(folder,'runtime-named.wasm'),watPath=join(folder,'runtime.wat');
  writeFileSync(namedPath,decorated);const disassembleArgs=[namedPath,'-o',watPath];run(tools['wasm-dis'].path,disassembleArgs);
  const decoded=inventory(folder,binary,names),functions=decoded.functions;
  const provenance={ref,commit,runtimeSha256:hash(binary),runtimeBytes:binary.length,rebuildByteEqual:true,
    executableSha256:hash(executable(binary)),diagnosticExecutableEqual:true,namedRuntimeSha256:hash(decorated),
    normalizedLfInputs:manifest.inputs,compilerFlags:manifest.flags,compileArgs,optimizeArgs,disassembleArgs,sourceDirectory:inputs,
    functionCount:functions.size,manifestSha256:hash(JSON.stringify(manifest)),types:decoded.types,watSha256:decoded.watSha256};
  save(join(folder,'provenance.json'),provenance);return {provenance,functions};
}

const before=rebuild('baseline',values['baseline-ref']),after=rebuild('candidate',values['candidate-ref']);
const profiles=(values.profile??[]).map(path=>{
  const absolute=resolve(root,path),bytes=readFileSync(absolute),profile=JSON.parse(bytes);
  return {path:relative(root,absolute),sha256:hash(bytes),git:profile.git,runtimeSha256:profile.provenance?.runtimeSha256,
    samples:(profile.results??[]).flatMap(result=>(result.runs??[]).flatMap((trial,repeat)=>(trial.workFrames??trial.captureFrames??[])
      .filter(frame=>frame.name?.startsWith('native.')).map(frame=>({case:result.id,repeat,symbol:frame.name.replace(/^native\.[^.]+\./,''),selfSamples:frame.selfSamples,inclusiveSamples:frame.inclusiveSamples}))))};
});
// Each normalization run gets its own directory, so stale preliminary diffs
// cannot be mistaken for the current summary's classification after --reuse.
const diffs=mkdtempSync(join(out,'function-diffs-'));
const all=[...new Set([...before.functions.keys(),...after.functions.keys()])].sort(),rows=[];
for(const symbol of all){
  const old=before.functions.get(symbol),now=after.functions.get(symbol);
  const rawEqual=!!old&&!!now&&old.rawSha256===now.rawSha256,normalizedEqual=!!old&&!!now&&old.normalizedSha256===now.normalizedSha256;
  const status=!old?'added':!now?'removed':normalizedEqual?(rawEqual?'identical':'relocation-only'):'body-changed';
  const row={symbol,status,rawEqual,normalizedEqual,before:old?{index:old.index,bytes:old.size,rawSha256:old.rawSha256,normalizedSha256:old.normalizedSha256}:null,
    after:now?{index:now.index,bytes:now.size,rawSha256:now.rawSha256,normalizedSha256:now.normalizedSha256}:null,
    historicalProfiles:profiles.flatMap(profile=>profile.samples.filter(v=>v.symbol===symbol).map(sample=>({...sample,path:profile.path,
      exactBaselineRuntime:profile.runtimeSha256===before.provenance.runtimeSha256,exactCandidateRuntime:profile.runtimeSha256===after.provenance.runtimeSha256})))};
  if(status!=='identical'){
    const safe=symbol.replace(/[^a-zA-Z0-9_.$-]/g,'_');assert.equal(safe,symbol,'unsafe symbol filename');
    const oldPath=join(diffs,safe+'.before.wat'),newPath=join(diffs,safe+'.after.wat');
    writeFileSync(oldPath,old?.normalizedWat??'');writeFileSync(newPath,now?.normalizedWat??'');
    const diff=spawnSync('git',['diff','--no-index','--no-ext-diff','--text','--',oldPath,newPath],{encoding:'utf8',maxBuffer:32*1024*1024});
    if(diff.error)throw diff.error;assert.ok(diff.status===0||diff.status===1,diff.stderr);
    const diffPath=join(diffs,safe+'.diff');writeFileSync(diffPath,diff.stdout);row.diff=relative(out,diffPath);
  }
  rows.push(row);
}
for(const [path,expected] of workingGuard)assert.equal(hash(readFileSync(resolve(root,path))),expected,'production changed during diagnostics: '+path);
const report={schema:'micromusic-device-function-comparison-v1',createdAt:new Date().toISOString(),git:{head:text(['rev-parse','HEAD']),status:text(['status','--short'])},
  scriptSha256,scriptSourceNormalization:'UTF-8 with CRLF normalized to LF',scriptSnapshot:'compare-source.mjs',
  tools,canonicalizerChecks,before:before.provenance,after:after.provenance,
  method:{normalization:'Function indices are resolved by the exact optimized symbol map and diagnostic custom function names. Only token objects in actual (type $N) uses are replaced by SHA-256 of their structural function signature. Independent local/label identifiers are never replaced, including identical $N spellings. Whitespace/comments do not enter normalized body hashes. S-expression structure and all other WAT tokens, constants, locals, branch labels and global/table names remain unchanged.',
    categories:'identical = raw body and normalized tokens equal; relocation-only = raw body differs but symbol/type-normalized tokens equal; body-changed = normalized tokens differ (not a proof of semantic inequivalence); added/removed = optimized symbol absent on one side.',
    limits:'No workload, performance measurements or new profiles. Historical profile annotations preserve their commit/runtime identities; samples from a different runtime are not fresh hotness evidence. Optimizer symbol matching is exact by name, with no guessed clone correspondence. Structural function-body equality does not recursively prove callee equality. Module/code layout and engine-generated machine code are not measured.'},
  profiles:profiles.map(({samples,...profile})=>profile),counts:Object.fromEntries(['identical','relocation-only','body-changed','added','removed'].map(status=>[status,rows.filter(row=>row.status===status).length])),functions:rows,productionUnmodified:true};
save(join(out,'summary.json'),report);
console.table(rows.filter(row=>row.status!=='identical').map(row=>({symbol:row.symbol,status:row.status,before:row.before?.bytes,after:row.after?.bytes,
  historicalSelfSamples:row.historicalProfiles.reduce((n,v)=>n+v.selfSamples,0)})));
console.log(JSON.stringify(report.counts));console.log('Static comparison: '+relative(root,join(out,'summary.json')));
