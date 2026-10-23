import {spawn} from 'node:child_process';
import {readFileSync,writeFileSync,appendFileSync,mkdirSync,readdirSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {parseArgs} from 'node:util';
import {root,buildCandidate,variants,hash,normalized} from '../tests/helpers/native-candidates.mjs';
import {checkMutants} from './check-optimization-mutants.mjs';
const {values}=parseArgs({options:{emsdk:{type:'string'},quick:{type:'boolean'},report:{type:'string'}}});
const sdk=values.emsdk||process.env.EMSDK;
if(!sdk)throw new Error('Set EMSDK or pass --emsdk <directory>; tools/setup.ps1 installs the verified SDK');
const output=join(root,'build/avr-optimization-tests');mkdirSync(output,{recursive:true});
const testRoot=join(root,'web-player/tests'),all=readdirSync(testRoot).filter(name=>name.endsWith('.test.mjs')).sort();
const kernel=all.filter(name=>/^(avr-|audio\.|core\.)/.test(name));
const extended=['extended/avr-long-run.test.mjs'];
const loader=new URL('../tests/helpers/native-test-loader.mjs',import.meta.url).href;
const report={
  schema:'micromusic-avr-optimization-tests-v1',runtime:process.version,status:'running',
  sourceSha256:hash(normalized(join(root,'web-player/native/avr.c'))),
  publishedWasmSha256:hash(readFileSync(join(root,'web-player/wasm/avr.wasm'))),
  mode:values.quick?'kernel-only':'kernel-plus-full-combined-and-endurance',runs:[]
};
const inputs=[...all,...extended,...readdirSync(join(testRoot,'helpers')).filter(n=>n.endsWith('.mjs')).map(n=>'helpers/'+n),
  'fixtures/block-optimizations.json','../scripts/test-optimizations.mjs','../scripts/check-optimization-mutants.mjs'];
report.testInputs=Object.fromEntries(inputs.map(name=>[name,hash(normalized(join(testRoot,name)))]));
async function run(label,files,candidate){
  const log=join(output,label+'.tap');writeFileSync(log,'');
  const args=[...(candidate?['--import',loader]:[]),'--test','--test-reporter=tap',...files.map(name=>join(testRoot,name))];
  const env={...process.env};delete env.MICROMUSIC_AVR_TEST_MODULE;delete env.MICROMUSIC_AVR_TEST_MANIFEST;
  if(candidate){env.MICROMUSIC_AVR_TEST_MODULE=candidate.binaryPath;env.MICROMUSIC_AVR_TEST_MANIFEST=candidate.manifestPath;}
  console.log('Running '+label+' ('+files.length+' files)…');
  const started=performance.now();
  const code=await new Promise((resolve,reject)=>{
    const child=spawn(process.execPath,args,{cwd:root,env,stdio:['ignore','pipe','pipe']});
    child.stdout.on('data',chunk=>appendFileSync(log,chunk));child.stderr.on('data',chunk=>appendFileSync(log,chunk));
    child.on('error',reject);child.on('close',resolve);
  });
  const text=readFileSync(log,'utf8'),count=key=>Number(text.match(new RegExp('^# '+key+' (\\d+)$','m'))?.[1]??NaN);
  const result={label,files,passed:count('pass'),failed:count('fail'),skipped:count('skipped'),
    durationMs:performance.now()-started,...(candidate?{candidate:candidate.provenance}:{})};
  report.runs.push(result);
  writeFileSync(values.report?resolve(values.report):join(output,'results.json'),JSON.stringify(report,null,2)+'\n');
  if(code!==0||!(result.passed>0)||result.failed!==0||result.skipped!==0)
    throw new Error(label+' failed; inspect '+log+'\n'+text.slice(-5000));
  console.log(label+': '+result.passed+' passed, 0 failures, 0 skipped');
}
await run('published-kernel',kernel);
const candidates={};
for(const variant of variants){
  candidates[variant]=buildCandidate(variant,sdk,output);
  await run(variant+'-kernel',kernel,candidates[variant]);
}
if(!values.quick){
  const completed=await Promise.allSettled([
    run('combined-player',all,candidates['budget-alu']),
    run('combined-endurance',extended,candidates['budget-alu'])
  ]);
  const failures=completed.filter(result=>result.status==='rejected').map(result=>result.reason);
  if(failures.length)throw new AggregateError(failures,'Combined candidate validation failed');
}
report.mutations=checkMutants(resolve(sdk),output);
console.log('Both deliberately broken candidates were rejected by the expected regression tests');
report.status='passed';
writeFileSync(values.report?resolve(values.report):join(output,'results.json'),JSON.stringify(report,null,2)+'\n');
console.log('Optimization validation complete. Report: '+(values.report?resolve(values.report):join(output,'results.json')));
