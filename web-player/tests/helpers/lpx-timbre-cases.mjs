// Deterministic synthetic controls. No recorded audio or fitted source values.
const tau=2*Math.PI;
const pcm16=value=>Math.max(-32768,Math.min(32767,Math.round(value)));

export function renderPartials(rate,partials,{duration=.48,onset=.035,attack=.003,decay=.28,level=9000,phases=[]}={}) {
  const pcm=new Int16Array(Math.round(rate*duration));
  const allowed=partials.filter(partial=>partial.frequency>0&&partial.frequency<rate/2);
  // Preserve level when a different actual rate excludes an upper partial.
  const peak=partials.reduce((sum,partial)=>sum+Math.abs(partial.amplitude??1),0)||1;
  for(let i=0;i<pcm.length;++i) {
    const time=i/rate-onset;if(time<0)continue;
    let value=0;
    for(let j=0;j<allowed.length;++j) {
      const partial=allowed[j],envelope=Math.min(1,time/attack)*Math.exp(-time/(partial.decay??decay));
      value+=(partial.amplitude??1)*envelope*Math.sin(tau*partial.frequency*time+(phases[j]??0));
    }
    pcm[i]=pcm16(level*value/peak);
  }
  return pcm;
}

// The in-band case distinguishes a timbre failure from a bandwidth limit.
// The bright case separately exercises an audible partial above a 4 kHz limit.
export const inharmonicPartials=Object.freeze([
  {frequency:613,amplitude:1,decay:.36},
  {frequency:1439,amplitude:.85,decay:.3},
  {frequency:2521,amplitude:.75,decay:.24},
  {frequency:3371,amplitude:.7,decay:.19}
]);
export const brightPartials=Object.freeze([
  {frequency:2731,amplitude:.3,decay:.32},
  {frequency:5837,amplitude:1,decay:.28},
  {frequency:9721,amplitude:.4,decay:.22}
]);

export function timbreCases(rate=8000) {
  const bell=renderPartials(rate,inharmonicPartials);
  const chimePartials=[{frequency:733,amplitude:1},{frequency:1901,amplitude:.9},{frequency:3037,amplitude:.8}];
  const chime=renderPartials(rate,chimePartials,{duration:.4,onset:.11,attack:.001,decay:.11});
  const chordPartials=[{frequency:401,amplitude:1},{frequency:659,amplitude:.9},{frequency:997,amplitude:.8}];
  const chord=renderPartials(rate,chordPartials,{duration:.4,attack:.02,decay:1});
  const speechPartials=Array.from({length:12},(_,i)=>({frequency:(i+1)*137,amplitude:1/(i+1)}));
  const speech=renderPartials(rate,speechPartials,{duration:.4,onset:.025,attack:.025,decay:.8});
  const highPartials=[{frequency:rate*.39,amplitude:1,decay:.055}];
  const highRing=renderPartials(rate,highPartials,{duration:.64,onset:.02,attack:.001,level:6000});
  const highPair=[{frequency:rate*.34,amplitude:.7,decay:.06},{frequency:rate*.44,amplitude:1,decay:.045}];
  const highTwoTone=renderPartials(rate,highPair,{duration:.64,onset:.02,attack:.001,level:6000});
  const noise=new Int16Array(Math.round(rate*.4));let state=0x6d2b79f5,previous=0;
  for(let i=0;i<noise.length;++i) {
    state=(Math.imul(state,1664525)+1013904223)>>>0;
    const raw=((state>>>16)-32768)/8,time=i/rate;
    const envelope=time<.07?0:Math.min(1,(time-.07)/.003)*Math.exp(-(time-.07)/.075);
    noise[i]=pcm16((raw-previous)*envelope);previous=raw;
  }
  return [
    {name:'inharmonic-bell',rate,reference:bell,partials:inharmonicPartials},
    {name:'short-chime',rate,reference:chime,partials:chimePartials},
    {name:'three-tone',rate,reference:chord,partials:chordPartials},
    {name:'noise-attack',rate,reference:noise,partials:[]},
    {name:'harmonic-control',rate,reference:speech,partials:speechPartials},
    {name:'high-ring',rate,reference:highRing,partials:highPartials},
    {name:'high-two-tone',rate,reference:highTwoTone,partials:highPair},
    {name:'silence',rate,reference:new Int16Array(Math.round(rate*.12)),partials:[]}
  ];
}

// A carrier-to-ring transition exercises carried synthesis/spectrum history.
// Measure the later ring alone, so a successful carrier cannot hide its loss.
export function transitionTimbreCases(rate=8000) {
  const duration=1.12,onset=.417,carrierEnd=.46;
  const carrierPartials=Array.from({length:12},(_,i)=>({frequency:(i+1)*137,amplitude:1/(i+1)}));
  const carrier=renderPartials(rate,carrierPartials,{duration,onset:.025,attack:.025,decay:1.4,level:9000});
  const cases=[
    {name:'harmonic-to-high-ring',partials:[{frequency:rate*.375,amplitude:1,decay:.075}]},
    {name:'harmonic-to-upper-ring',partials:[{frequency:rate*.417,amplitude:1,decay:.075}]},
    {name:'harmonic-to-bright-pair',partials:[
      {frequency:rate*.283,amplitude:.45,decay:.17},
      {frequency:rate*.39,amplitude:1,decay:.075}
    ]}
  ];
  return cases.map(c=>{
    const reference=renderPartials(rate,c.partials,{duration,onset,attack:.001,level:6000});
    for(let i=0;i<reference.length;++i) {
      const fade=Math.max(0,Math.min(1,(carrierEnd-i/rate)/.06));
      reference[i]=pcm16(reference[i]+Math.round(carrier[i]*fade));
    }
    return {...c,rate,reference,window:{start:Math.ceil((carrierEnd+.015)*rate),end:Math.floor((onset+.5)*rate)}};
  });
}

// Independent radix-2 DFT used only by tests; not the production C++ evaluator.
function powerSpectrum(pcm,offset,size) {
  const real=new Float64Array(size),imaginary=new Float64Array(size);
  for(let i=0;i<size;++i) {
    const at=offset+i;
    real[i]=(at>=0&&at<pcm.length?pcm[at]:0)*(.5-.5*Math.cos(tau*i/(size-1)));
  }
  for(let i=1,j=0;i<size;++i) {
    let bit=size>>1;for(;j&bit;bit>>=1)j^=bit;j^=bit;
    if(i<j) {[real[i],real[j]]=[real[j],real[i]];[imaginary[i],imaginary[j]]=[imaginary[j],imaginary[i]];}
  }
  for(let length=2;length<=size;length<<=1) {
    const angle=-tau/length,stepReal=Math.cos(angle),stepImaginary=Math.sin(angle);
    for(let start=0;start<size;start+=length) {
      let wr=1,wi=0;
      for(let j=0;j<length/2;++j) {
        const a=start+j,b=a+length/2;
        const vr=real[b]*wr-imaginary[b]*wi,vi=real[b]*wi+imaginary[b]*wr;
        real[b]=real[a]-vr;imaginary[b]=imaginary[a]-vi;real[a]+=vr;imaginary[a]+=vi;
        const next=wr*stepReal-wi*stepImaginary;wi=wr*stepImaginary+wi*stepReal;wr=next;
      }
    }
  }
  return Float64Array.from({length:size/2+1},(_,k)=>(real[k]**2+imaginary[k]**2)*(k===0||k===size/2?1:2));
}

function analyze(pcm,rate,partials) {
  const size=2**Math.ceil(Math.log2(rate*.04)),hop=size/4;
  const spectrum=new Float64Array(size/2+1),frames=[];
  for(let at=-hop;at<pcm.length;at+=hop) {
    const power=powerSpectrum(pcm,at,size);let total=0;
    for(let k=0;k<power.length;++k) {spectrum[k]+=power[k];total+=power[k];}
    frames.push(total);
  }
  const energy=spectrum.reduce((sum,value)=>sum+value,0);
  const frequencies=partials.map(x=>typeof x==='number'?x:x.frequency).filter(f=>f>0&&f<rate/2);
  const powers=frequencies.map(f=>{
    const center=Math.round(f*size/rate);let sum=0;
    for(let k=Math.max(1,center-1);k<=Math.min(size/2,center+1);++k)sum+=spectrum[k];
    return sum;
  });
  return {size,hop,spectrum,frames,energy,frequencies,powers};
}

function shapeError(reference,candidate) {
  const a=reference.reduce((s,v)=>s+v,0),b=candidate.reduce((s,v)=>s+v,0);
  if(!a)return b?1:0;if(!b)return 1;
  let error=0;
  for(let i=0;i<reference.length;++i)error+=(Math.sqrt(reference[i]/a)-Math.sqrt(candidate[i]/b))**2/2;
  return Math.max(0,Math.min(1,error));
}

export function measureTimbre(reference,candidate,rate,partials=[]) {
  if(reference.length!==candidate.length||!reference.length||!Number.isInteger(rate)||rate<1000)throw Error('Expected equal nonempty PCM and an actual sample rate.');
  const a=analyze(reference,rate,partials),b=analyze(candidate,rate,partials);
  let envelopeError=0;
  for(let i=0;i<a.frames.length;++i)envelopeError+=(Math.sqrt(a.frames[i])-Math.sqrt(b.frames[i]))**2;
  envelopeError=a.energy?envelopeError/a.energy:b.energy?1:0;
  const total=a.powers.reduce((s,v)=>s+v,0);
  const supported=a.powers.map(v=>total>0&&v>=total*.03);
  const retention=a.powers.map((v,i)=>v>0?Math.min(1,Math.sqrt(b.powers[i]/v)):0);
  return {
    spectralShapeError:shapeError(a.spectrum,b.spectrum),
    partialShapeError:shapeError(a.powers,b.powers),envelopeError,
    frequencies:a.frequencies,sourcePartials:supported.filter(Boolean).length,
    retainedPartials:retention.filter((v,i)=>supported[i]&&v>=.2).length,
    partialRetention:retention,
    minimumPartialRetention:Math.min(1,...retention.filter((_,i)=>supported[i])),
    energyRatio:a.energy?b.energy/a.energy:b.energy?null:1
  };
}

export function spectrumBandFraction(pcm,rate,low,high) {
  const a=analyze(pcm,rate,[]);let energy=0;
  for(let k=0;k<a.spectrum.length;++k)if(k*rate/a.size>=low&&k*rate/a.size<high)energy+=a.spectrum[k];
  return a.energy?energy/a.energy:0;
}
