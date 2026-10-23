import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {join,resolve} from 'node:path';

export const root=fileURLToPath(new URL('../../../',import.meta.url));
export const hash=data=>createHash('sha256').update(data).digest('hex');
export const normalized=path=>readFileSync(path,'utf8').replaceAll('\r\n','\n');
export const fixture=JSON.parse(readFileSync(new URL('../fixtures/block-optimizations.json',import.meta.url)));
export const variants=['budget','alu','budget-alu'];
export function candidateSource(source,variant){
  if(!variants.includes(variant))throw new Error('Unknown candidate '+variant);
  if(hash(source)!==fixture.baseSourceSha256)throw new Error('AVR C source changed: review and update optimization fixture');
  for(const name of variant.split('-')){
    const {before,after}=fixture.edits[name];
    if(source.split(before).length!==2)throw new Error('Candidate edit must match exactly once: '+name);
    source=source.replace(before,after);
  }
  return source;
}
export function buildCandidate(variant,sdk,outputRoot){
  const baseline=JSON.parse(readFileSync(join(root,'web-player/wasm/build.json')));
  for(const [path,expected] of Object.entries(baseline.inputs)){
    if(hash(normalized(join(root,path)))!==expected)throw new Error('Published build input is stale: '+path);
  }
  const source=candidateSource(normalized(join(root,'web-player/native/avr.c')),variant);
  const output=join(outputRoot,variant);mkdirSync(output,{recursive:true});
  const sourcePath=join(output,'avr.c'),binaryPath=join(output,'avr.wasm');
  writeFileSync(sourcePath,source);
  const compiler=join(resolve(sdk),'upstream/bin',process.platform==='win32'?'clang.exe':'clang');
  const flags=baseline.flags.map(flag=>flag.replaceAll('<emsdk>',resolve(sdk)));
  const result=spawnSync(compiler,[...flags,sourcePath,'-lc','-lclang_rt.builtins','-o',binaryPath],{encoding:'utf8'});
  if(result.error)throw result.error;
  if(result.status!==0)throw new Error(result.stderr||result.stdout);
  const version=spawnSync(compiler,['--version'],{encoding:'utf8'});
  if(version.error||version.status!==0)throw version.error??new Error(version.stderr);
  const provenance={
    schema:'micromusic-avr-test-candidate-v1',variant,baseSourceSha256:fixture.baseSourceSha256,
    fixtureSha256:hash(normalized(fileURLToPath(new URL('../fixtures/block-optimizations.json',import.meta.url)))),
    sourceSha256:hash(source),wasmSha256:hash(readFileSync(binaryPath)),
    compiler:version.stdout.split(/\r?\n/)[0],flags:baseline.flags
  };
  const manifestPath=join(output,'candidate.json');
  writeFileSync(manifestPath,JSON.stringify(provenance,null,2)+'\n');
  return {binaryPath,manifestPath,provenance};
}
