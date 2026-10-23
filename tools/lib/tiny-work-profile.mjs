// Observe production instructions without changing the emulated clock or state.
// Each slot starts at Timer0 enable, then at the previous OCR0B output write.
export function traceForeground(cpu,waitPcBytes){
  if(!Number.isInteger(waitPcBytes)||waitPcBytes<0||waitPcBytes>1022||waitPcBytes%2)
    throw new Error('wait PC must be an even ATtiny13 Flash byte address');
  const originalStep=cpu.step;
  let slot=null,outputs=0,readyCount=0,finishCount=0,firstStart=null;
  let minReady=Infinity,maxReady=0,minFinish=Infinity,maxFinish=0,minSlack=Infinity;
  let maxReadySample=null,maxFinishSample=null,minSlackSample=null;
  function start(cycle){slot={start:cycle,ready:null,finish:null,index:outputs};}
  cpu.step=function(){
    const beforeTimer=this.timer,beforeReady=this.r[8],beforeWrites=this.writes;
    originalStep.call(this);
    if(!beforeTimer&&this.timer){
      if(slot)throw new Error('Timer0 restarted during foreground timing trace');
      firstStart=this.cyc;start(this.cyc);
    }
    if(this.writes!==beforeWrites){
      if(this.writes!==beforeWrites+1||!slot||slot.ready===null||slot.finish===null)
        throw new Error(`PWM slot ${outputs} ended before foreground work was complete`);
      const slack=this.cyc-slot.finish;
      if(slack<minSlack){minSlack=slack;minSlackSample=slot.index;}
      outputs++;start(this.cyc);
    }
    if(slot&&!beforeReady&&this.r[8]){
      if(slot.ready!==null)throw new Error(`PWM slot ${slot.index} prepared more than one sample`);
      slot.ready=this.cyc;readyCount++;
      const elapsed=this.cyc-slot.start;
      minReady=Math.min(minReady,elapsed);
      if(elapsed>maxReady){maxReady=elapsed;maxReadySample=slot.index;}
    }
    // A non-output IRQ may return to the existing wait loop many times.
    // The first arrival after readiness is the single completion for this slot.
    if(slot&&slot.ready!==null&&slot.finish===null&&!this.inIRQ&&
       this.pc*2===waitPcBytes&&this.r[8]){
      slot.finish=this.cyc;finishCount++;
      const elapsed=this.cyc-slot.start;
      minFinish=Math.min(minFinish,elapsed);
      if(elapsed>maxFinish){maxFinish=elapsed;maxFinishSample=slot.index;}
    }
  };
  function report(){
    return {engine:'reference-instruction-trace',waitPcBytes,
      slotOrigin:'Timer0 enable for sample 0; preceding OCR0B write thereafter',
      includesInterruptCycles:true,includesEEPROMWaitCycles:true,
      includesPhaseAndFrameParsing:true,oneTimeInitializationExcluded:true,
      timerStartCycle:firstStart,preparedSamples:readyCount,completedSamples:finishCount,
      closedOutputSlots:outputs,periodBudgetCycles:1280,conservativeDeadlineCycles:1279,
      minimumReadyCycles:Number.isFinite(minReady)?minReady:null,maximumReadyCycles:maxReady||null,
      minimumCompletionCycles:Number.isFinite(minFinish)?minFinish:null,maximumCompletionCycles:maxFinish||null,
      minimumSlackCycles:Number.isFinite(minSlack)?minSlack:null,
      maximumReadySample:maxReadySample,maximumCompletionSample:maxFinishSample,
      minimumSlackSample:minSlackSample};
  }
  return {report,assertComplete(expected){
    if(outputs!==expected||readyCount!==expected||finishCount!==expected)
      throw new Error(`Foreground timing counts differ: outputs=${outputs}, ready=${readyCount}, complete=${finishCount}, expected=${expected}`);
    if(maxReady>=1279||maxFinish>=1279||minSlack<=0)
      throw new Error(`Foreground misses its slot budget: ready=${maxReady}, complete=${maxFinish}, slack=${minSlack}`);
  }};
}
