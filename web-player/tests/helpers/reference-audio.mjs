import { AVRCore } from '../../lib/avr-reference.js';
import { parseHex } from '../../lib/hex.js';

// Independent Direct Form I oracle; production C uses transposed Direct Form II.
// Coefficients: W3C Audio EQ Cookbook, LPF/HPF, Q=0.5.
export class ReferenceFilter {
  constructor(rate,cutoff=4000,volume=1){
    this.rate=rate;this.volume=volume;
    this.hp=this.section(35,true);this.lp=this.section(Math.min(cutoff,rate*.45),false);
  }
  section(hz,highpass){
    const theta=2*Math.PI*hz/this.rate,cos=Math.cos(theta),alpha=Math.sin(theta)/(2*.5);
    const b=highpass?[(1+cos)/2,-1-cos,(1+cos)/2]:[(1-cos)/2,1-cos,(1-cos)/2];
    return {b:b.map(v=>v/(1+alpha)),a:[-2*cos/(1+alpha),(1-alpha)/(1+alpha)],x:[0,0],y:[0,0]};
  }
  sectionSample(f,x){
    const y=f.b[0]*x+f.b[1]*f.x[0]+f.b[2]*f.x[1]-f.a[0]*f.y[0]-f.a[1]*f.y[1];
    f.x[1]=f.x[0];f.x[0]=x;f.y[1]=f.y[0];f.y[0]=y;return y;
  }
  sample(x){return this.sectionSample(this.lp,this.sectionSample(this.hp,x))*this.volume;}
  process(input){return Float32Array.from(input,x=>this.sample(x));}
}
export class ReferenceRenderer {
  constructor(entry,rate,{filtered=true,cutoff=4000,volume=1}={}){
    this.core=new AVRCore(parseHex(entry.flashHex),entry.eepromHex?parseHex(entry.eepromHex,64):null);
    this.ratio=entry.pwmHz/rate;this.phase=0;this.first=true;this.frames=0;
    this.filtered=filtered;this.filter=new ReferenceFilter(rate,cutoff,volume);
  }
  render(count){
    const out=new Float32Array(count),raw=new Float32Array(count);
    if(this.first){this.v0=this.core.nextDuty();this.v1=this.core.nextDuty();this.first=false;}
    for(let i=0;i<count;i++){
      raw[i]=(this.v0+(this.v1-this.v0)*this.phase-128)/128;
      out[i]=this.filtered?this.filter.sample(raw[i]):raw[i];
      this.phase+=this.ratio;
      while(this.phase>=1){this.phase--;this.v0=this.v1;this.v1=this.core.nextDuty();}
    }
    this.frames+=count;this.rawSamples=raw;return out;
  }
}
