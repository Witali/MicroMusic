// Diagnostic source-map reconstruction; production sources and WASM stay intact.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {resolve,join,dirname,parse,relative,isAbsolute,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {auditV8NativeProfile,validateV8NativeFunctions} from './lib/avr-v8-native-profile.mjs';
import {loadInlineArtifacts} from './lib/avr-inline-artifacts.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{input:{type:'string'},emsdk:{type:'string'},python:{type:'string'},
  'out-dir':{type:'string',default:'build/profiles/native-source-map'},
  'test-tap':{type:'string'},
  'inline-scopes':{type:'string'},'inline-report':{type:'string'},
  output:{type:'string',default:'build/profiles/native-source-audit.json'}}});
assert.ok(values.input,'Pass --input with a completed V8 log/disassembly capture');
const input=resolve(root,values.input),out=resolve(root,values['out-dir']);
const underBuild=p=>{const rel=relative(resolve(root,'build'),p);return rel&&!isAbsolute(rel)&&rel!=='..'&&!rel.startsWith('..'+sep);};
assert.ok(underBuild(input)&&underBuild(out),'Raw diagnostics must stay in build/');
mkdirSync(out,{recursive:true});
const read=p=>readFileSync(resolve(root,p)),json=p=>JSON.parse(read(p));
const hash=b=>createHash('sha256').update(b).digest('hex');
const text=p=>read(p).toString('utf8').replaceAll('\r\n','\n');
const manifest=json('web-player/wasm/device-build.json'),native=read('web-player/wasm/attiny13a.wasm');
assert.equal(hash(native),manifest.artifacts['attiny13a.wasm']);
for(const [path,expected]of Object.entries(manifest.inputs))assert.equal(hash(text(path)),expected,'Stale native source');
const summary=json(join(input,'summary.json'));
assert.equal(summary.complete,true,'Incomplete capture');
assert.equal(summary.provenance.runtimeRebuildByteEqual,true);
assert.equal(summary.provenance.runtimeSha256,hash(native),'Capture uses another native version');
assert.equal(summary.node.version,process.version,'Use the captured Node version');
assert.equal(summary.node.versions.v8,process.versions.v8,'Use the captured V8 version');
for(const result of summary.results)for(const run of result.runs){
  assert.equal(run.productionEquality,true,'Capture lacks production parity');
  assert.equal(run.architectureSha256,result.referenceArchitectureSha256,'Reference architecture differs');
  if(summary.parameters.nativeLogOnly)assert.ok(run.captureMode==='native-log-only-v1'&&
    !Object.hasOwn(run,'profile'),'Native-only capture has an inconsistent mode');
}
assert.ok(!summary.parameters.nativeLogOnly||summary.parameters.nativeLogWindows,
  'Native-only capture lacks native window metadata');
const captureProducer='web-player/scripts/profile-device.mjs';
const windows=summary.parameters.nativeLogWindows?summary.results.flatMap(result=>result.runs.map(run=>{
  assert.ok(run.nativeLogWindow&&Object.keys(run.nativeLogWindow).length===1&&
    typeof run.nativeLogWindow.label==='string','Missing or invalid native capture window');
  return {label:run.nativeLogWindow.label,workWallMs:run.workWallMs};
})):null;
if(windows){
  assert.ok(windows.length,'No native capture windows');
  assert.equal(summary.provenance.sourceSha256NormalizedLF[captureProducer],hash(text(captureProducer)),
    'Window capture uses another producer revision');
}
function sections(b){
  assert.ok(b.subarray(0,8).equals(Buffer.from([0,97,115,109,1,0,0,0])),'Invalid WASM');
  let p=8;const rows=[];
  const u32=()=>{let n=0;for(let s=0;s<35;s+=7){assert.ok(p<b.length);const v=b[p++];n+=(v&127)*2**s;if(!(v&128))return n;}throw Error('Invalid LEB');};
  while(p<b.length){const start=p,id=b[p++],size=u32(),end=p+size;assert.ok(end<=b.length);rows.push({id,start,end});p=end;}
  return rows;
}
const executable=b=>Buffer.concat([b.subarray(0,8),...sections(b).filter(s=>s.id).map(s=>b.subarray(s.start,s.end))]);
const originalSections=sections(native).filter(s=>s.id);
const named=read(join(input,'runtime-named.wasm'));
assert.equal(hash(named),summary.provenance.namedRuntimeSha256);
assert.ok(executable(named).equals(executable(native)),'Named capture changed native code');
assert.deepEqual(sections(named).filter(s=>s.id),originalSections,'Named capture uses another byte-offset layout');
const functions=json(join(input,'runtime-functions.json'));
validateV8NativeFunctions(functions,named);
const log=text(join(input,'v8.log'));
assert.equal(log.match(/^profiler,begin,\d+$/gm)?.length,1,'Missing or duplicate V8 profiler begin');
assert.equal(log.match(/^profiler,end$/gm)?.length,1,'Incomplete V8 profiler log');

let sourceMap,mappedBytes,finalMap,sourceMapTool,inlineContexts,inlineProvenance;
assert.equal(!!values['inline-scopes'],!!values['inline-report'],'Pass both --inline-scopes and --inline-report');
if(values['inline-scopes']){
  const directory=resolve(root,values['inline-scopes']);assert.ok(underBuild(directory),'Raw inline data must stay in build/');
  const loaded=loadInlineArtifacts({root,directory,reportPath:resolve(root,values['inline-report']),nativeSha256:hash(native),manifest});
  ({sourceMap,mappedBytes,inlineContexts}=loaded);finalMap=loaded.mapPath;inlineProvenance=loaded.provenance;
}else{
  let sdk=values.emsdk||process.env.EMSDK;
  for(let parent=root;!sdk;parent=dirname(parent)){
    const candidate=join(parent,'build/toolchains/emscripten-6.0.12');
    if(existsSync(join(candidate,'upstream/bin/clang.exe')))sdk=candidate;
    if(parent===parse(parent).root)break;
  }
  assert.ok(sdk,'Pass --emsdk pointing at the registered prepared SDK');sdk=resolve(sdk);
  const bin=join(sdk,'upstream/bin'),python=values.python||process.env.PYTHON||'python';
  const tool=name=>join(bin,name+(process.platform==='win32'?'.exe':''));
  const run=(command,args,env=process.env)=>{
    const r=spawnSync(command,args,{cwd:root,env,encoding:'utf8',maxBuffer:16*1024*1024});
    assert.equal(r.status,0,r.stderr||String(r.error));return r.stdout;
  };
  const pre=join(out,'runtime-debug-preopt.wasm'),mapped=join(out,'runtime-mapped.wasm');
  const preMap=join(out,'preopt.map');finalMap=join(out,'runtime.map');
  run(tool('clang'),[...manifest.flags.map(s=>s.replaceAll('<emsdk>',sdk)),'--no-wasm-opt','-g',
    '-fdebug-prefix-map='+root.replace(/[\\/]$/,'')+'=.',...manifest.sources,'-lc','-lclang_rt.builtins','-o',pre]);
  // The source map carries locations through normal O3. Retaining DWARF with -g
  // during Binaryen optimization can inhibit passes and fails exact-code parity.
  const config=join(out,'emscripten-config.py');
  writeFileSync(config,'LLVM_ROOT = '+JSON.stringify(bin.replaceAll('\\','/'))+'\n'+
    'BINARYEN_ROOT = '+JSON.stringify(join(sdk,'upstream').replaceAll('\\','/'))+'\n'+
    'NODE_JS = ['+JSON.stringify(process.execPath.replaceAll('\\','/'))+']\n'+
    'CACHE = '+JSON.stringify(join(sdk,'upstream/emscripten/cache').replaceAll('\\','/'))+'\n');
  sourceMapTool=join(sdk,'upstream/emscripten/tools/wasm-sourcemap.py');
  run(python,[sourceMapTool,pre,'--dwarfdump',tool('llvm-dwarfdump'),'-o',preMap],{...process.env,EM_CONFIG:config});
  run(tool('wasm-opt'),[pre,'-O3','--input-source-map',preMap,'--output-source-map',finalMap,'-o',mapped]);
  mappedBytes=read(mapped);sourceMap=json(finalMap);
}
assert.ok(executable(mappedBytes).equals(executable(native)),'Source-map build changes executable sections');
assert.deepEqual(sections(mappedBytes).filter(s=>s.id),originalSections,'Source map uses another byte-offset layout');
const audit=auditV8NativeProfile({log,
  disassembly:text(join(input,'run.log')),functions,sourceMap,...(windows?{windows}:{}),...(inlineContexts?{inlineContexts}:{})});
const tickTimes=log.split('\n').filter(line=>line.startsWith('tick,')).map(line=>Number(line.split(',')[2])).sort((a,b)=>a-b);
const gaps=tickTimes.slice(1).map((time,n)=>time-tickTimes[n]).sort((a,b)=>a-b);
for(const row of audit.sourceLines){
  assert.ok(Object.hasOwn(manifest.inputs,row.source),'Unregistered project source location');
  assert.ok(row.line>0&&row.line<=text(row.source).split('\n').length,'Source line outside current input');
}
const paths=['web-player/wasm/device-build.json','web-player/scripts/audit-native-source-profile.mjs',
  'web-player/scripts/lib/avr-v8-native-profile.mjs','web-player/tests/avr-v8-native-profile.test.mjs',captureProducer];
paths.push('web-player/scripts/audit-device-profile.mjs');
paths.push('web-player/scripts/lib/avr-inline-profile.mjs','web-player/scripts/lib/avr-inline-artifacts.mjs');
paths.push('web-player/tests/avr-inline-artifacts.test.mjs');
const report={schema:'micromusic-native-source-profile-v1',
  node:process.version,v8:process.versions.v8,native:{bytes:native.length,sha256:hash(native),
    executableSha256:hash(executable(native)),sourceMapExecutableEqual:true,sourceMapByteOffsetsEqual:true,
    functionMetadataMatchesNamedWasm:true},
  compilerVersion:manifest.compilerVersion,
  sources:Object.fromEntries(paths.map(p=>[p,hash(text(p))])),
  nativeInputs:manifest.inputs,
  inputs:Object.fromEntries(['summary.json','v8.log','run.log','runtime-functions.json','runtime-named.wasm']
    .map(p=>[p,hash(read(join(input,p)))])),
  mapping:{sha256:hash(read(finalMap)),sources:sourceMap.sources.length,
    sourceMapGeneratorSha256:inlineProvenance?.sourceMapGeneratorSha256??hash(read(sourceMapTool)),
    embeddedSourceContents:!!sourceMap.sourcesContent?.some(Boolean),...(inlineProvenance?{inline:inlineProvenance}:{})},
  rawTickGaps:{scope:'Whole-process adjacent raw tick timestamp gaps; not work durations or source ownership.',
    count:gaps.length,minUs:gaps[0]??null,medianUs:gaps.length?
      (gaps.length%2?gaps[gaps.length>>1]:(gaps[gaps.length/2-1]+gaps[gaps.length/2])/2):null,
    maxUs:gaps.at(-1)??null},
  workload:{parameters:summary.parameters,ids:summary.results.map(r=>r.id),
    captureProducerSha256:summary.provenance.sourceSha256NormalizedLF[captureProducer],
    scope:windows?'Whole-process ticks remain conserved. Native timer markers and a conservative boundary allowance separate certain-interior, boundary and outside views; verified function containers preserve source-map gaps, while source ownership remains a candidate, with no exclusive subsystem duration claim.':
      'Whole-process V8 leaf ticks include construction, warmup, reference and capture. Verified function containers do not imply source or subsystem ownership. No exact work window or exclusive elapsed-time claim.'},
  audit};
if(values['test-tap']){
  const bytes=read(values['test-tap']),tap=bytes.toString();
  const counts=Object.fromEntries(['tests','pass','fail','cancelled','skipped','todo'].map(key=>{
    const match=tap.match(new RegExp('^# '+key+' (\\d+)$','m'));assert.ok(match,'Incomplete test TAP');
    return [key,Number(match[1])];
  }));
  assert.ok(counts.tests>0&&counts.tests===counts.pass);
  assert.equal(counts.fail+counts.cancelled+counts.skipped+counts.todo,0);
  report.tests={...counts,tapSha256:hash(bytes)};
}
const output=resolve(root,values.output);mkdirSync(dirname(output),{recursive:true});
writeFileSync(output,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({sourceMapExecutableEqual:true,...audit.budget}));
