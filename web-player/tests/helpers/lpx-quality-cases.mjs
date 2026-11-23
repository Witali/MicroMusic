// Integer-only synthetic inputs, mirrored by the development oracle generator.
export function qualityCases() {
  const cases=[];
  for(const rate of [8000,12000,16000])for(const name of ['voiced','quiet','silence','transient','clipped','short']) {
    const count=name==='voiced'?rate*2+17:name==='quiet'?rate+7:name==='silence'?Math.floor(rate/10)+1:
      name==='transient'?rate+53:name==='clipped'?Math.floor(rate/2)+1:Math.floor(rate*2/5)-1;
    const reference=new Int16Array(count),candidate=new Int16Array(count);
    let state=0x12345678,phase=0,previous=0;
    for(let i=0;i<count;i++) {
      state=(Math.imul(1664525,state)+1013904223)>>>0;
      const noise=(state>>>24)-128;
      const frequency=120+Math.floor(i/Math.floor(rate/5))%5*20;
      phase=(phase+frequency)%rate;
      const level=6000+Math.floor(i/Math.floor(rate/7))%3*4000;
      let x=Math.floor(phase*level*2/rate)-level,y=Math.trunc((3*x+previous)/4)+noise;
      if(name==='quiet') { x=phase<rate/2?-1:1;y=i%17?previous:0; }
      if(name==='silence') { x=0;y=i%71===0?100:0; }
      if(name==='transient') { x=i%137===0?20000:i%137===1?-20000:noise*2;y=Math.trunc((x+previous)/2); }
      if(name==='clipped') { x=(i%64-32)*1000;y=Math.max(-32768,Math.min(32767,x*2)); }
      reference[i]=x;candidate[i]=y;previous=x;
    }
    cases.push({name,rate,reference,candidate});
  }
  return cases;
}

// Synthetic 16 kHz high-pass noise; no input/output alignment or gain fitting.
export function qualityTemporalCases() {
  const rate=16000,count=8193,envelope=[0,1,4,2,0,3,4,0];
  const carrier=new Int16Array(count);
  let state=0x2468ace0,previous=0,older=0;
  for(let i=0;i<count;i++) {
    state=(Math.imul(1664525,state)+1013904223)>>>0;
    const raw=(state>>>16)-32768;
    carrier[i]=Math.trunc((raw-2*previous+older)/8);older=previous;previous=raw;
  }
  const cases=[];
  for(const name of ['phase-noise','delayed-envelope','flat-envelope','lost-high-band','tail-noise','silence','silence-tail']) {
    const reference=new Int16Array(count),candidate=new Int16Array(count);
    for(let i=0;i<count;i++) {
      let x=Math.trunc(carrier[i]*envelope[Math.floor(i/256)%envelope.length]/4),y=x;
      if(name==='phase-noise')y=-x;
      if(name==='delayed-envelope')y=Math.trunc(carrier[i]*(i<256?0:envelope[Math.floor((i-256)/256)%envelope.length])/4);
      if(name==='flat-envelope')y=Math.trunc(carrier[i]/2);
      if(name==='lost-high-band') { let sum=0;for(let k=0;k<8&&k<=i;k++)sum+=Math.trunc(carrier[i-k]*envelope[Math.floor((i-k)/256)%envelope.length]/4);y=Math.trunc(sum/8); }
      if(name==='tail-noise') { x=i>=count-35?carrier[i]:0;y=0; }
      if(name==='silence'||name==='silence-tail') { x=0;y=name==='silence-tail'&&i===count-1?1:0; }
      reference[i]=x;candidate[i]=y;
    }
    cases.push({name,rate,reference,candidate});
  }
  return cases;
}
