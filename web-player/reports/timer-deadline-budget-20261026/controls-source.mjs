import assert from 'node:assert/strict';

export const controlLabels=Object.freeze(['oldA','oldB','newA','newB']);
// Williams design: every label occupies every position and precedes every
// other label once in four rows. The next four rows reverse those orders.
const orders=[[0,1,3,2],[1,2,0,3],[2,3,1,0],[3,0,2,1]];
export function controlSchedule(trials){
  assert.ok(Number.isInteger(trials)&&trials>=8&&trials<=32&&trials%8===0,'trials must be8/16/24/32');
  return Array.from({length:trials},(_,trial)=>{
    const order=orders[trial%4].map(index=>controlLabels[index]);
    return trial%8<4?order:order.reverse();
  });
}
export function statistics(values){
  assert.ok(values.length>0&&values.every(v=>Number.isFinite(v)&&v>0),'finite positive observations required');
  const sorted=[...values].sort((a,b)=>a-b),n=sorted.length;
  return {median:n%2?sorted[n>>1]:(sorted[n/2-1]+sorted[n/2])/2,min:sorted[0],max:sorted.at(-1)};
}
export function controlRatios(runs,trials){
  const schedule=controlSchedule(trials);assert.equal(runs.length,trials*4);
  const pairs=[];
  for(let trial=0;trial<trials;trial++){
    const row=runs.filter(run=>run.trial===trial);
    assert.deepEqual(row.map(run=>run.variant),schedule[trial],'recorded order must match the design');
    row.forEach((run,position)=>{assert.equal(run.position,position);statistics([run.ms]);});
    const time=id=>row.find(run=>run.variant===id).ms;
    pairs.push({trial,oldIdentity:time('oldA')/time('oldB'),newIdentity:time('newA')/time('newB'),
      crossVersion:Math.sqrt((time('oldA')/time('newA'))*(time('oldB')/time('newB')))});
  }
  return {pairs,...Object.fromEntries(['oldIdentity','newIdentity','crossVersion']
    .map(key=>[key,statistics(pairs.map(pair=>pair[key]))]))};
}
