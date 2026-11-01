import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,rmSync} from 'node:fs';
import {join,dirname,resolve,basename} from 'node:path';
import {tmpdir} from 'node:os';
import {createHash} from 'node:crypto';
import {loadInlineArtifacts} from '../scripts/lib/avr-inline-artifacts.mjs';

const hash=value=>createHash('sha256').update(value).digest('hex');
function fixture(t){
  const root=mkdtempSync(join(tmpdir(),'micromusic-inline-'));
  t.after(()=>{assert.equal(dirname(root),resolve(tmpdir()));assert.ok(basename(root).startsWith('micromusic-inline-'));rmSync(root,{recursive:true,force:true});});
  const directory=join(root,'raw');mkdirSync(directory);
  const source='web-player/native/peripherals/device.c';mkdirSync(dirname(join(root,source)),{recursive:true});writeFileSync(join(root,source),'probe\n');
  const paths=['web-player/scripts/map-native-inline-scopes.py','web-player/scripts/lib/avr_dwarf_scopes.py','web-player/scripts/probe-source-map-labels.py'];
  const sourceHashes=Object.fromEntries(paths.map(path=>{mkdirSync(dirname(join(root,path)),{recursive:true});writeFileSync(join(root,path),'fixture\n');return [path,hash('fixture\n')];}));
  const contexts={schema:'micromusic-dwarf-inline-contexts-v1',frames:{1:{kind:'project',source,function:'probe',line:1}},contexts:[{kind:'unique',chains:[[1]]}]};
  const files={'dwarf-verification.txt':'fixture','preopt-dwarf.txt':'fixture','regenerated-preopt.map':'{}',
    'inline-contexts.json':JSON.stringify(contexts),'scoped.input.map':'{}','scoped.output.map':'{}','scoped.wasm':'fixture'};
  for(const [name,data]of Object.entries(files))writeFileSync(join(directory,name),data);
  const proof={schema:'micromusic-native-inline-transport-v1',nativeSha256:hash('native'),inlineScopesExtracted:true,
    llvmDwarfVerified:true,sourceMapRegenerationEqual:true,executableSectionsAndOffsetsEqual:true,
    exclusiveDurationsMeasured:false,profileSamplesJoined:false,sourceHashes,
    scopeMeaning:'Pre-Binaryen DWARF4 candidates, not a post-optimization dynamic call stack',sourceMapGeneratorSha256:hash('generator'),
    artifacts:Object.fromEntries(Object.entries(files).map(([name,data])=>[name,hash(data)]))};
  const reportPath=join(root,'proof.json'),sync=()=>{writeFileSync(reportPath,JSON.stringify(proof));writeFileSync(join(directory,'report.json'),JSON.stringify(proof));};sync();
  return {root,directory,reportPath,nativeSha256:proof.nativeSha256,manifest:{inputs:{[source]:hash('probe\n')}},proof,sync};
}
test('inline loader binds exact artifact and producer hashes plus registered source coordinates',t=>{
  const f=fixture(t),value=loadInlineArtifacts(f);assert.equal(value.inlineContexts.contexts.length,1);
  assert.equal(value.provenance.llvmDwarfVerified,true);assert.equal(value.provenance.reportSha256,hash(readFileSync(f.reportPath)));
});
test('missing producer identity cannot pass by comparing two absent values',t=>{
  const f=fixture(t);delete f.proof.sourceHashes['web-player/scripts/lib/avr_dwarf_scopes.py'];f.sync();
  assert.throws(()=>loadInlineArtifacts(f),/Missing inline producer/);
});
test('changed artifact bytes and changed producer source reject the retained identity',t=>{
  const f=fixture(t);writeFileSync(join(f.directory,'scoped.wasm'),'changed');
  assert.throws(()=>loadInlineArtifacts(f),/artifact differs/);
  writeFileSync(join(f.directory,'scoped.wasm'),'fixture');writeFileSync(join(f.root,'web-player/scripts/probe-source-map-labels.py'),'changed');
  assert.throws(()=>loadInlineArtifacts(f),/Stale inline producer/);
});
test('matching digest updates cannot legitimize extra private frame fields or invalid source lines',t=>{
  const f=fixture(t),path=join(f.directory,'inline-contexts.json'),original=JSON.parse(readFileSync(path));
  for(const mutate of [d=>d.frames[1].extra='confidential',d=>d.frames[1].line=99]){
    const value=structuredClone(original);mutate(value);const text=JSON.stringify(value);writeFileSync(path,text);
    f.proof.artifacts['inline-contexts.json']=hash(text);f.sync();
    assert.throws(()=>loadInlineArtifacts(f),e=>/inline|Inline/.test(e.message)&&!e.message.includes('confidential'));
  }
});
test('malformed JSON and unknown artifact keys fail without printing their contents',t=>{
  const f=fixture(t);writeFileSync(f.reportPath,'confidential-invalid-json');
  assert.throws(()=>loadInlineArtifacts(f),e=>e.message==='Invalid inline JSON data');
  f.proof.artifacts['confidential-name']=hash('fixture');f.sync();
  assert.throws(()=>loadInlineArtifacts(f),e=>/artifact names/.test(e.message)&&!e.message.includes('confidential'));
});
