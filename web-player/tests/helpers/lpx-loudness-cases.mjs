export function loudnessCases() {
  const cases=[];
  for(const rate of [8000,12000,16000]) {
    const tone=(n,amp,freq=1000)=>Int16Array.from({length:n},(_,i)=>Math.round(amp*Math.sin(2*Math.PI*freq*i/rate)));
    for(const freq of [100,1000,3000])cases.push({name:`tone-${freq}`,rate,pcm:tone(rate*2,3000,freq)});
    cases.push({name:'quiet',rate,pcm:tone(rate*2,64)});
    cases.push({name:'loud',rate,pcm:tone(rate*2,24000)});
    cases.push({name:'silence',rate,pcm:new Int16Array(rate*2)});
    cases.push({name:'below-gate',rate,pcm:tone(rate*2,1)});
    cases.push({name:'short',rate,pcm:tone(rate*4/10-1,3000)});
    cases.push({name:'one-block',rate,pcm:tone(rate*4/10,3000)});
    cases.push({name:'partial-tail',rate,pcm:tone(rate*2+37,3000)});
    const pauses=tone(rate*4,3000);for(let i=0;i<pauses.length;i++)if(i<rate || i>=rate*2)pauses[i]=0;
    cases.push({name:'pauses',rate,pcm:pauses});
    const transient=tone(rate*2,100);transient[rate]=32767;
    cases.push({name:'peak-limited',rate,pcm:transient});
    let seed=0x45e2a17;
    cases.push({name:'noise',rate,pcm:Int16Array.from({length:rate*2},()=>{seed^=seed<<13;seed^=seed>>>17;seed^=seed<<5;return (seed>>16)/4;})});
    cases.push({name:'dc',rate,pcm:new Int16Array(rate*2).fill(-32768)});
  }
  return cases;
}
