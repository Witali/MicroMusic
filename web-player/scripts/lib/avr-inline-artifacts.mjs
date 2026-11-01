// Bind private diagnostic artifacts to the retained proof and current sources.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {prepareInlineContexts} from './avr-inline-profile.mjs';

export function loadInlineArtifacts({root,directory,reportPath,nativeSha256,manifest}){
  const read=p=>readFileSync(p),json=p=>{try{return JSON.parse(read(p));}catch{throw Error('Invalid inline JSON data');}},
    hash=b=>createHash('sha256').update(b).digest('hex'),digest=value=>typeof value==='string'&&/^[0-9a-f]{64}$/.test(value);
  const proof=json(reportPath),raw=json(join(directory,'report.json'));
  assert.ok(proof.schema==='micromusic-native-inline-transport-v1','Invalid inline proof schema');
  assert.ok(proof.nativeSha256===nativeSha256&&raw.nativeSha256===nativeSha256,'Inline native version differs');
  for(const key of ['schema','inlineScopesExtracted','llvmDwarfVerified','sourceMapRegenerationEqual','executableSectionsAndOffsetsEqual']){
    assert.ok(raw[key]===proof[key],'Inline proof differs');if(key!=='schema')assert.ok(proof[key]===true,'Unverified inline proof');
  }
  assert.ok(proof.exclusiveDurationsMeasured===false&&proof.profileSamplesJoined===false,'Invalid inline proof scope');
  const producerPaths=['web-player/scripts/map-native-inline-scopes.py','web-player/scripts/lib/avr_dwarf_scopes.py',
    'web-player/scripts/probe-source-map-labels.py'];
  const permitted=new Set([...producerPaths,'web-player/tests/dwarf-inline-scopes.test.py','web-player/tests/source-map-labels.test.py']);
  for(const path of producerPaths){
    assert.ok(digest(proof.sourceHashes?.[path]),'Missing inline producer identity');
    assert.ok(raw.sourceHashes?.[path]===proof.sourceHashes[path],'Inline producer identity differs');
  }
  for(const [path,expected]of Object.entries(proof.sourceHashes)){
    assert.ok(permitted.has(path),'Unregistered inline producer source');
    assert.ok(digest(expected)&&hash(Buffer.from(read(join(root,path)).toString().replaceAll('\r\n','\n')))===expected,'Stale inline producer');
  }
  const names=['dwarf-verification.txt','preopt-dwarf.txt','regenerated-preopt.map','inline-contexts.json',
    'scoped.input.map','scoped.output.map','scoped.wasm'];
  assert.ok(JSON.stringify(Object.keys(proof.artifacts).sort())===JSON.stringify([...names].sort()),'Invalid inline artifact names');
  assert.ok(JSON.stringify(Object.keys(raw.artifacts).sort())===JSON.stringify([...names].sort()),'Invalid raw inline artifact names');
  for(const name of names){
    assert.ok(digest(proof.artifacts[name])&&raw.artifacts[name]===proof.artifacts[name],'Inline artifact identity differs');
    assert.ok(hash(read(join(directory,name)))===proof.artifacts[name],'Inline artifact differs');
  }
  const scopeMeaning='Pre-Binaryen DWARF4 candidates, not a post-optimization dynamic call stack';
  assert.ok(proof.scopeMeaning===scopeMeaning&&digest(proof.sourceMapGeneratorSha256),'Invalid inline provenance');
  const contexts=json(join(directory,'inline-contexts.json'));prepareInlineContexts(contexts);
  const checkCoordinate=entry=>{
    assert.ok(Object.hasOwn(manifest.inputs,entry.source),'Unregistered inline project source');
    const text=read(join(root,entry.source)).toString().replaceAll('\r\n','\n');
    const lines=text.split('\n').length-(text.endsWith('\n')?1:0);
    assert.ok(entry.line>0&&entry.line<=lines,'Inline line outside current source');
  };
  for(const frame of Object.values(contexts.frames)){
    if(frame.kind==='project')checkCoordinate(frame);
    if(frame.callsite)checkCoordinate(frame.callsite);
  }
  return {sourceMap:json(join(directory,'scoped.output.map')),inlineContexts:contexts,
    mappedBytes:read(join(directory,'scoped.wasm')),mapPath:join(directory,'scoped.output.map'),
    provenance:{reportSha256:hash(read(reportPath)),artifacts:proof.artifacts,producerSources:proof.sourceHashes,
      sourceMapGeneratorSha256:proof.sourceMapGeneratorSha256,scopeMeaning,
      llvmDwarfVerified:true,sourceMapRegenerationEqual:true}};
}
