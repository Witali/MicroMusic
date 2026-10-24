import {test} from 'node:test';
import assert from 'node:assert/strict';
import {controlLabels,controlSchedule,controlRatios} from '../scripts/lib/runtime-control-design.mjs';

test('control schedule balances every position and every directed adjacent pair',()=>{
  for(const trials of [8,16,24,32]){
    const rows=controlSchedule(trials),positions=new Map(),adjacent=new Map();
    assert.equal(rows.length,trials);
    for(const row of rows){
      assert.deepEqual([...row].sort(),[...controlLabels].sort());
      for(let i=0;i<4;i++){
        const key=row[i]+i;positions.set(key,(positions.get(key)||0)+1);
        if(i<3){const pair=row[i]+'>'+row[i+1];adjacent.set(pair,(adjacent.get(pair)||0)+1);}
      }
    }
    assert.equal(positions.size,16);assert.ok([...positions.values()].every(n=>n===trials/4));
    assert.equal(adjacent.size,12);assert.ok([...adjacent.values()].every(n=>n===trials/4));
  }
});

const observations=()=>controlSchedule(8).flatMap((row,trial)=>row.map((variant,position)=>
  ({trial,position,variant,ms:variant.startsWith('old')?20:10})));
test('identity controls remain one while a known cross-version cost is recovered',()=>{
  const result=controlRatios(observations(),8);
  assert.deepEqual(result.oldIdentity,{median:1,min:1,max:1});
  assert.deepEqual(result.newIdentity,{median:1,min:1,max:1});
  assert.deepEqual(result.crossVersion,{median:2,min:2,max:2});
});
test('invalid observations and ordering cannot silently produce a benchmark summary',()=>{
  for(const trials of [0,4,7,9,33])assert.throws(()=>controlSchedule(trials));
  assert.throws(()=>controlRatios(observations().slice(1),8));
  for(const value of [0,-1,NaN,Infinity]){const rows=observations();rows[0].ms=value;assert.throws(()=>controlRatios(rows,8));}
  const reordered=observations();[reordered[0],reordered[1]]=[reordered[1],reordered[0]];
  assert.throws(()=>controlRatios(reordered,8));
  const wrongPosition=observations();wrongPosition[0].position=3;assert.throws(()=>controlRatios(wrongPosition,8));
});
