import {test} from 'node:test';
import assert from 'node:assert/strict';
import {traceForeground} from './lib/tiny-work-profile.mjs';

function fake(){
  return {timer:false,r:new Uint8Array(32),writes:0,pc:0,cyc:0,inIRQ:false,
    next:null,step(){Object.assign(this,this.next);}};
}
function step(cpu,state){cpu.next=state;cpu.step();}

test('full completion includes parsing and IRQ time, counting one wait per output slot',()=>{
  const cpu=fake(),profile=traceForeground(cpu,54);
  step(cpu,{timer:true,cyc:100});
  const firstReady=new Uint8Array(32);firstReady[8]=1;
  step(cpu,{r:firstReady,cyc:450});
  step(cpu,{pc:27,cyc:600});
  step(cpu,{inIRQ:true,pc:3,cyc:850});
  step(cpu,{inIRQ:false,pc:27,cyc:880}); // Existing wait, not a second completion.
  step(cpu,{inIRQ:true,pc:40,writes:1,cyc:1397});
  step(cpu,{r:new Uint8Array(32),cyc:1398});
  step(cpu,{inIRQ:false,pc:27,cyc:1410}); // Return after clear does not finish slot 1.
  const ready=new Uint8Array(32);ready[8]=1;
  step(cpu,{r:ready,pc:90,cyc:1800});
  step(cpu,{pc:27,cyc:2000});
  step(cpu,{inIRQ:true,pc:40,writes:2,cyc:2677});
  profile.assertComplete(2);
  const report=profile.report();
  assert.equal(report.preparedSamples,2);assert.equal(report.completedSamples,2);
  assert.equal(report.maximumReadyCycles,403);
  assert.equal(report.maximumCompletionCycles,603);
  assert.equal(report.minimumSlackCycles,677);
  assert.equal(report.maximumCompletionSample,1);
});

test('output before the frame parser returns to wait is rejected',()=>{
  const cpu=fake();traceForeground(cpu,54);
  step(cpu,{timer:true,cyc:10});
  const ready=new Uint8Array(32);ready[8]=1;
  step(cpu,{r:ready,cyc:50});
  assert.throws(()=>step(cpu,{writes:1,cyc:1290}),/before foreground work was complete/);
});

test('even completed output is rejected when the foreground exceeds the conservative budget',()=>{
  const cpu=fake(),profile=traceForeground(cpu,54);
  step(cpu,{timer:true,cyc:10});
  const ready=new Uint8Array(32);ready[8]=1;
  step(cpu,{r:ready,cyc:100});
  step(cpu,{pc:27,cyc:1289});
  step(cpu,{writes:1,cyc:1307,inIRQ:true});
  assert.throws(()=>profile.assertComplete(1),/misses its slot budget/);
});
