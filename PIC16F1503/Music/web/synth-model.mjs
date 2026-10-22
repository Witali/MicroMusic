/* Sound-model reference for the MicroMusic PIC16F1503 port.
 * This is NOT instruction-level PIC execution. It mirrors firmware/main.c's
 * score interpreter, envelopes, 16-bit DDS, LFSR and PWM duty production.
 */
import {MUSIC_ASSETS as A} from './music-assets.mjs';
export class SoundModel {
  constructor(){this.reset();}
  reset(){
    this.v=Array.from({length:3},()=>({phase:0,step:0,env:0,stage:0,age:0,decay:0,frame:0}));
    this.drumEnv=0;this.drumMode=0;this.beatIndex=0;this.drumLfsr=0xace1;this.drumPhase=0;
    this.musicDivider=0;this.envelopeTicks=0;this.remainingGrid=0;this.sectionIndex=0;this.scoreOffset=0;this.gridPhase=0;
    this.sectionsTraversed=0;this.noteoffs=0;this.eventCount=0;this.pwm=128;this.muted=[false,false,false,false];
    this.advanceEvent();
  }
  startNote(n,step){const v=this.v[n];v.step=step;v.age=0;v.decay=0;v.frame=0;v.stage=1;v.env=n===0?1:15;}
  noteOff(n){this.noteoffs++;if(this.v[n].env)this.v[n].stage=0;}
  triggerDrum(mode){this.drumMode=mode;this.drumEnv=15;if(mode===0)this.drumPhase=0;}
  envelopeTick(){
    this.envelopeTicks=(this.envelopeTicks+1)&255;
    for(let i=0;i<3;i++){
      const v=this.v[i];if(!v.env)continue;
      if(v.age<255)v.age++;
      if(v.frame<3){let period=i===1?6:4;if(i===0)period=20;if(v.age>=(v.frame+1)*period)v.frame++;}
      if(v.stage===0){if(++v.decay>=2){v.decay=0;v.env--;}}
      else if(i===0){if(v.stage===1 && ((++v.decay&3)===0)){
        if(v.env<14)v.env++; else v.stage=2;
      }}else{
        const high=v.step>=1500;
        const period=i===1?(high?9:17):(high?7:12);
        if(++v.decay>=period){v.decay=0;if(v.env)v.env--;v.stage=2;}
      }
    }
    if(this.drumEnv){const rate=this.drumMode===2?3:1;if((this.envelopeTicks%rate)===0)this.drumEnv--;}
  }
  advanceEvent(){
    let guard=0;
    while(guard++<32){
      if(this.scoreOffset>=A.score.length){this.scoreOffset=0;this.sectionIndex=0;}
      let e=A.score[this.scoreOffset++];this.eventCount++;
      if(e===255){this.sectionIndex++;this.sectionsTraversed++;
        if(this.sectionIndex>=A.playlist.length)this.sectionIndex=0;
        this.scoreOffset=A.playlist[this.sectionIndex];continue;
      }
      if(e>=0xf0){if(e&1)this.noteOff(0);if(e&2)this.noteOff(1);if(e&4)this.noteOff(2);if(e&8)this.drumEnv=0;continue;}
      if(e>=0xe0){const j=e&15;if(j<5){this.startNote(1,A.chordsKey[j]);this.startNote(2,A.chordsPluck[j]);}continue;}
      const idx=e>>3, duration=e&7;
      this.remainingGrid=duration<7?A.durations[duration]:1;
      if(idx===13)this.noteOff(0);else if(idx<13)this.startNote(0,A.noteSteps[idx]);
      return;
    }
    this.remainingGrid=1;
  }
  stepGrid(){
    if((this.beatIndex&1)===0){
      if(this.beatIndex===0)this.triggerDrum(0);
      else if(this.beatIndex===4)this.triggerDrum(1);
      else this.triggerDrum(2);
    }
    this.beatIndex=(this.beatIndex+1)&7;
    if(this.remainingGrid && --this.remainingGrid===0)this.advanceEvent();
  }
  wave(inst,v){const idx=v.phase>>>12,hi=v.step>=(inst===0?1450:1500);
    if(inst===0)return A.violin[(hi<<4)|idx];
    if(inst===1)return A.piano[(hi<<6)|(v.frame<<4)|idx];
    return A.guitar[(hi<<6)|(v.frame<<4)|idx];
  }
  drumSample(){
    if(!this.drumEnv)return 0;
    const old=this.drumLfsr&255;
    this.drumLfsr=((this.drumLfsr>>>1)^((this.drumLfsr&1)?0xb400:0))&65535;
    const n=this.drumLfsr&255;
    if(this.drumMode===0){this.drumPhase=(this.drumPhase+180+this.drumEnv*42)&65535;
      const tone=((this.drumPhase>>>11)&31)-16;
      return (tone*this.drumEnv)>>4;
    }
    if(this.drumMode===1){const raw=(n&31)-16,body=((this.drumPhase>>>11)&15)-8;
      this.drumPhase=(this.drumPhase+300)&65535;
      return ((raw+body)*this.drumEnv)>>5;
    }
    return ((((n^old)&31)-16)*this.drumEnv)>>5;
  }
  nextSample(){
    if(++this.musicDivider===64){const prev=this.gridPhase;this.musicDivider=0;this.envelopeTick();this.gridPhase=(this.gridPhase+A.gridInc)&65535;
      if(this.gridPhase<prev)this.stepGrid();
    }
    let mix=128;
    for(let i=0;i<3;i++){const v=this.v[i];v.phase=(v.phase+v.step)&65535;
      if(v.env && !this.muted[i])mix+=Math.trunc((this.wave(i,v)*v.env)/4);
    }
    const drum=this.drumSample();if(!this.muted[3])mix+=drum;
    this.pwm=Math.max(0,Math.min(255,mix));return this.pwm;
  }
  /* For emulator: Timer2 postscaler generates 1 ISR every 4 PWM cycles.
   * Preview stream reconstructs duty held over those four carrier periods. */
  generate(count){const a=new Uint8Array(count);for(let i=0;i<count;i++)a[i]=this.nextSample();return a;}
}
