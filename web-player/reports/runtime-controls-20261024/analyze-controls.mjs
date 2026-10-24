// Recheck retained raw observations and regenerate the descriptive tables.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
const dir=dirname(fileURLToPath(import.meta.url));
const hash=b=>createHash('sha256').update(b).digest('hex');
const read=name=>JSON.parse(readFileSync(join(dir,name)));
const median=values=>{const sorted=[...values].sort((a,b)=>a-b),n=sorted.length;return n%2?sorted[n>>1]:(sorted[n/2-1]+sorted[n/2])/2;};
const labels=['oldA','oldB','newA','newB'];
const stats=values=>({median:median(values),min:Math.min(...values),max:Math.max(...values),aboveOne:values.filter(v=>v>1).length});
function validate(report,sourceName){
  assert.equal(report.complete,true);const trials=report.parameters.trials;
  for(const pair of [['oldA','oldB'],['newA','newB']])
    assert.deepEqual(report.provenance.runtimes[pair[0]],report.provenance.runtimes[pair[1]]);
  const source=readFileSync(join(dir,sourceName),'utf8').replaceAll('\r\n','\n');
  assert.equal(hash(source),report.provenance.sourceSha256['web-player/scripts/benchmark-runtime-controls.mjs']);
  const helper=readFileSync(join(dir,'control-design-source.txt'),'utf8').replaceAll('\r\n','\n');
  assert.equal(hash(helper),report.provenance.sourceSha256['web-player/scripts/lib/runtime-control-design.mjs']);
  const cases=[];
  for(const row of report.results){
    assert.equal(row.runs.length,trials*4);assert.equal(row.warmups.length,report.parameters.warmups*4);
    for(const label of labels)assert.equal(row.warmups.filter(run=>run.variant===label).length,report.parameters.warmups);
    for(const run of row.warmups)assert.equal(run.variant,report.parameters.schedule[run.pass][run.position]);
    const all=[...row.warmups,...row.runs],reference=all[0],positions=new Map(),adjacent=new Map();
    const actualDivisors=[...new Set(all.map(run=>run.finalState.clockDivisor))];
    const desired=row.id.match(/^kernel-(?:clki|internal)-20m-div(\d+)/);
    if(desired)assert.deepEqual(actualDivisors,[Number(desired[1])],row.id+' actual divisor');
    for(const run of all){
      assert.ok(Number.isFinite(run.ms)&&run.ms>0);
      for(const key of ['rawSha256','architectureSha256','pinSha256','finalState'])assert.deepEqual(run[key],reference[key],row.id+'/'+key);
    }
    const ratios={oldIdentity:[],newIdentity:[],crossVersion:[]};
    for(let trial=0;trial<trials;trial++){
      const runs=row.runs.filter(run=>run.trial===trial);assert.deepEqual(runs.map(run=>run.variant).sort(),labels.slice().sort());
      runs.forEach((run,position)=>{
        assert.equal(run.position,position);assert.equal(run.variant,report.parameters.schedule[trial][position]);
        const key=run.variant+position;positions.set(key,(positions.get(key)||0)+1);
        if(position<3){const key=run.variant+'>'+runs[position+1].variant;adjacent.set(key,(adjacent.get(key)||0)+1);}
      });
      const time=label=>runs.find(run=>run.variant===label).ms;
      ratios.oldIdentity.push(time('oldA')/time('oldB'));ratios.newIdentity.push(time('newA')/time('newB'));
      ratios.crossVersion.push(Math.sqrt(time('oldA')*time('oldB'))/Math.sqrt(time('newA')*time('newB')));
    }
    assert.equal(positions.size,16);assert.ok([...positions.values()].every(n=>n===trials/4));
    assert.equal(adjacent.size,12);assert.ok([...adjacent.values()].every(n=>n===trials/4));
    for(const [key,values] of Object.entries(ratios))assert.ok(Math.abs(median(values)-row.summary.ratios[key].median)<1e-12);
    cases.push({id:row.id,actualDivisors,desiredDivisor:desired?Number(desired[1]):null,
      intendedDivisorVerified:!desired||actualDivisors.length===1&&actualDivisors[0]===Number(desired[1]),
      ...Object.fromEntries(Object.entries(ratios).map(([key,values])=>[key,{...stats(values),pairs:values}]))});
  }
  return {sha256NormalizedLF:hash(readFileSync(join(dir,report===initial?'initial-six-case-controls.json':
    report===repeated?'explicit-div1-repeat.json':'service-inline-benchmark.json'),'utf8').replaceAll('\r\n','\n')),trials,
    measuredRuns:report.results.reduce((n,row)=>n+row.runs.length,0),warmupRuns:report.results.reduce((n,row)=>n+row.warmups.length,0),
    exactCheckpoints:report.results.reduce((n,row)=>n+row.validation.checkpointsCompared,0),cases};
}
const initial=read('initial-six-case-controls.json'),repeated=read('explicit-div1-repeat.json'),candidate=read('service-inline-benchmark.json');
const summary={schema:'micromusic-runtime-controls-analysis-v1',initial:validate(initial,'initial-harness-source.txt'),
  repeated:validate(repeated,'explicit-div1-harness-source.txt'),candidate:validate(candidate,'final-harness-source.txt')};
assert.ok(summary.initial.cases.every(row=>row.intendedDivisorVerified));
summary.divisorAudit={initialActual:1,repeatActual:1,ckdiv8Mask:16,
  reference:'web-player/vendor/microchip/ATtiny_DFP/3.4.278/include/avr/iotn13a.h',
  correction:'Initial divide8 suspicion was wrong; all recorded fixtures had their intended divisors.'};
let table='| Case | Old identity | New identity | Cross-version ratio | New faster trials |\n|---|---:|---:|---:|---:|\n';
for(const row of summary.candidate.cases)table+='| '+row.id+' | '+row.oldIdentity.median.toFixed(3)+' | '+row.newIdentity.median.toFixed(3)+' | '+row.crossVersion.median.toFixed(3)+'x | '+row.crossVersion.aboveOne+'/'+summary.candidate.trials+' |\n';
writeFileSync(join(dir,'analysis.json'),JSON.stringify(summary,null,2)+'\n');writeFileSync(join(dir,'candidate-table.txt'),table);console.log(table);
console.log('All recorded observations, source hashes, positions, adjacent pairs, exact parity and actual divisors verified.');
