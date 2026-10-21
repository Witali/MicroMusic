// Negative validation: the regression tests must reject these deliberate bugs.
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
import {root,candidateSource,normalized,hash} from '../tests/helpers/native-candidates.mjs';
export function checkMutants(sdk,output){
  const compiler=join(sdk,'upstream/bin',process.platform==='win32'?'clang.exe':'clang');
  const base=JSON.parse(readFileSync(join(root,'web-player/wasm/build.json')));
  const source=candidateSource(normalized(join(root,'web-player/native/avr.c')),'budget-alu');
  const cases=[
    {name:'lost-overflow-guard',before:'remaining=S(overflowAt)-S(cyc)-1',after:'remaining=S(overflowAt)-S(cyc)',
      test:'avr-optimization-regressions.test.mjs',pattern:'block budget',failure:/not ok \d+ - block budget/},
    {name:'lost-adc-carry',before:'o==ADC?flags&1:0',after:'0',
      test:'avr-blocks.test.mjs',pattern:'block ADC:',failure:/not ok \d+ - block ADC:/}
  ];
  const results=[];
  for(const item of cases){
    assert.equal(source.split(item.before).length,2);
    const dir=join(output,'mutants',item.name);mkdirSync(dir,{recursive:true});
    const src=join(dir,'avr.c'),wasm=join(dir,'avr.wasm');writeFileSync(src,source.replace(item.before,item.after));
    const compile=spawnSync(compiler,[...base.flags.map(f=>f.replaceAll('<emsdk>',sdk)),src,'-lc','-lclang_rt.builtins','-o',wasm],{encoding:'utf8'});
    if(compile.error)throw compile.error;assert.equal(compile.status,0,compile.stderr);
    const result=spawnSync(process.execPath,['--import',pathToFileURL(join(root,'web-player/tests/helpers/native-test-loader.mjs')).href,
      '--test','--test-reporter=tap','--test-name-pattern',item.pattern,join(root,'web-player/tests',item.test)],
      {env:{...process.env,MICROMUSIC_AVR_TEST_MODULE:wasm},encoding:'utf8',timeout:30000});
    if(result.error)throw result.error;
    writeFileSync(join(dir,'expected-failure.tap'),result.stdout+result.stderr);
    assert.equal(result.status,1);assert.match(result.stdout,item.failure,'Must fail the intended assertion, not module loading');
    results.push({mutation:item.name,sourceSha256:hash(readFileSync(src)),wasmSha256:hash(readFileSync(wasm)),
      expectedFailureDetected:true,test:item.test,pattern:item.pattern});
  }
  return results;
}
