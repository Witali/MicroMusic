// Independent host boundary/arithmetic tests. No generated media is retained.
#include "decoder.h"
#include <algorithm>
#include <array>
#include <iostream>
#include <stdexcept>
#include <vector>
using Co=std::array<int16_t,10>;
struct Writer {
 std::vector<uint8_t> data;size_t count=0;
 void put(uint16_t v,uint8_t n){for(uint8_t i=0;i<n;++i,++count){if(!(count&7))data.push_back(0);data[count/8]|=((v>>i)&1)<<(count&7);}}
 void run(unsigned n){unsigned z=0;while((1u<<(z+1))<=n)++z;put(0,z);put(1,1);put(n-(1u<<z),z);}
};
static void require(bool ok,const char* text){if(!ok)throw std::runtime_error(text);}
static int clip(int64_t v,int lo,int hi){return int(std::min<int64_t>(hi,std::max<int64_t>(lo,v)));}
static int floorPower(int64_t x,int bits){return x>=0?int(x/(1L<<bits)):-int((-x+(1L<<bits)-1)/(1L<<bits));}
static Co interpolate(const Co& a,const Co& b,int t){Co c;for(int k=0;k<10;++k)c[k]=a[k]+(int(b[k])-a[k])*t/8;return c;}
static uint16_t independentLog(int q){
 const int lut[]={4096,4277,4467,4664,4871,5087,5312,5547,5793,6049,6317,6597,6889,7194,7512,7845,8192};
 int i=(q&255)>>4,base=lut[i]+((lut[i+1]-lut[i])*(q&15)+8)/16;return uint16_t(((uint32_t(base)<<(q/256))+2048)/4096);
}
static void anchor(Writer& w,const Co& base,const Co& target,int plan,int code,int exponent){
 w.put(1,1);w.put(plan,2);int at=0;
 while(at<10){int length=plan==0?10:plan==1?5:plan==2?2:std::min(3,10-at);if(plan==3)w.put(length-1,4);w.put(code,3);
  if(code<5){w.put(exponent,4);for(int k=0;k<length;++k){int delta=int(target[at+k])-base[at+k];require(delta%(1<<exponent)==0,"Test mantissa divisibility");w.put(uint16_t(delta/(1<<exponent)),4+code*2);}}
  else if(code==5)for(int k=0;k<length;++k)w.put(uint16_t(target[at+k]),16);
  at+=length;
 }
}
static std::vector<uint8_t> header(const Writer& w,int n,int profile,bool extras){
 std::vector<uint8_t> b(13,0);b[0]='L';b[1]='G';b[2]=profile|(extras?128:0);
 auto word=[&](int at,unsigned value){b[at]=value;b[at+1]=value>>8;};word(3,8000);word(5,n);word(7,13926);word(9,4000);word(11,w.data.size());b.insert(b.end(),w.data.begin(),w.data.end());return b;
}
struct Fixture {std::vector<uint8_t> bytes;std::vector<Co> coefficients;std::vector<int> steps,gain,lag;int n,profile;bool extras;};
static void pitchLiteral(Writer& w,int gain,int lag){w.put(gain/2,3);if(gain)w.put(lag-18,7);}
static Fixture make(int n,int profile,bool extras,int plan,int code,int exponent,int scaleMode,int pitchMode){
 Fixture out;out.n=n;out.profile=profile;out.extras=extras;Writer w;Co end={};int blocks=(n+159)/160;
 for(int frame=0;frame*320<n;++frame){
  Co old=end,mid=end,next=end;bool changed=frame%3!=2;
  if(!frame){next[0]=-1200;next[1]=500;mid=next;}
  else if(changed&&code!=6){for(int k=0;k<10;++k){int delta=(k%3-1)*(1<<exponent);mid[k]=old[k]+delta;next[k]=mid[k]-delta;}}
  for(int sub=0;sub<16&&frame*320+sub*20<n;++sub){
   if(sub==0){w.put(changed,1);if(changed){if(!frame)anchor(w,old,next,plan,5,0);else anchor(w,old,mid,plan,code,exponent);}}
   if(sub==4&&changed&&frame)anchor(w,mid,next,plan,code,exponent);
   if(!frame||!changed)out.coefficients.push_back(next);
   else if(sub<4)out.coefficients.push_back(interpolate(old,mid,sub*2+1));
   else if(sub<8)out.coefficients.push_back(interpolate(mid,next,(sub-4)*2+1));else out.coefficients.push_back(next);
   if(!(sub&7)){
    int block=frame*2+sub/8,index=17+block%6;
    if(scaleMode==0){w.put(0,2);w.put(index,5);out.steps.push_back(lbg1::stepForScale(index));}
    else {if(!block){w.put(scaleMode,2);if(scaleMode==1){w.put(20,5);w.run(blocks);}else if(scaleMode==2){w.put(20,5);w.put(7,12);w.run(blocks);}else w.run(blocks);}
     if(scaleMode==3){w.put(index,5);out.steps.push_back(lbg1::stepForScale(index));}else out.steps.push_back(scaleMode==1?66:independentLog(1547+block*7));}
    int gain=2*(block%4+1),lag=18+block%30;
    if(pitchMode==0){w.put(0,2);pitchLiteral(w,gain,lag);}
    else {if(!block){w.put(pitchMode,2);if(pitchMode==1){pitchLiteral(w,6,37);w.run(blocks);}else if(pitchMode==2){w.put(3,3);w.put(31-18,7);w.put(1,8);w.run(blocks);}else w.run(blocks);}
     if(pitchMode==1){gain=6;lag=37;}else if(pitchMode==2){gain=6;lag=31+block;}else pitchLiteral(w,gain,lag);}
    out.gain.push_back(gain);out.lag.push_back(lag);
   }
   if(!(sub&1)){
    int packet=frame*8+sub/2;
    if(profile==4){w.put(packet%16,4);w.put(1,1);w.put((packet*7+3)%16,4);w.put(0,1);}
    else {int a=packet*7%20,b=(packet*11+3)%20;w.put((a&3)|((b&3)<<2),4);w.put((a>>2)+5*(b>>2),5);w.put(5,4);w.put(uint16_t(-3),4);}
    if(extras){w.put(1,1);w.put(packet*3%40,6);w.put(packet&1?2:uint16_t(-2),4);}
   }
  }
  end=next;
 }
 out.bytes=header(w,n,profile,extras);return out;
}
static std::vector<int16_t> reference(const Fixture& f){
 int16_t history[10]={};int8_t ring[256]={};int dd=0,previousClipped=0;std::vector<int16_t> pcm;
 for(int at=0;at<f.n;++at){int block=at/160,packet=at/40,within=at%40,q=floorPower(f.gain[block]*ring[(at-f.lag[block])&255]+8,4);
  int a,b,aa,ab;if(f.profile==4){a=packet%16;a+=(a+2)/4;b=(packet*7+3)%16;b+=(b+2)/4;aa=8;ab=-8;}
  else {a=packet*7%20;b=(packet*11+3)%20;aa=5;ab=-3;}
  if(within==a)q+=aa;if(within==b+20)q+=ab;if(f.extras&&within==packet*3%40)q+=packet&1?2:-2;
  q=clip(q,-32,31);ring[at&255]=q;int64_t value=q*f.steps[block];for(int k=0;k<10;++k)value-=floorPower(int64_t(f.coefficients[at/20][k])*history[k],12);
  int predicted=clip(value,-32767,32767);for(int k=9;k;--k)history[k]=history[k-1];history[0]=predicted;
  dd=clip(predicted+floorPower(int64_t(13926)*dd,14),-32767,32767);int cc=clip(dd,-16384,16384);
  int out=clip(cc-floorPower(int64_t(4000)*previousClipped,14),-16384,16384);previousClipped=cc;pcm.push_back(clip(out*2,-32768,32767));
 }return pcm;
}
struct Callback {const std::vector<uint8_t>* bytes;int failAt;};
static bool callback(void* p,uint16_t at,uint8_t* value){auto& c=*static_cast<Callback*>(p);if(at==c.failAt||at>=c.bytes->size())return false;*value=(*c.bytes)[at];return true;}
static void check(const Fixture& f){
 auto expected=reference(f);lbg1::Decoder d;require(d.begin(f.bytes.data(),f.bytes.size()),"Valid header");std::vector<int16_t> actual;int16_t value;
 while(d.nextS16(value))actual.push_back(value);require(!d.error()&&d.finished()&&actual==expected,"Independent PCM reference");require(!d.nextS16(value),"Exact EOF");
 Callback context{&f.bytes,-1};require(d.beginCallback(callback,&context,f.bytes.size()),"Callback begin");actual.clear();while(d.nextS16(value))actual.push_back(value);require(!d.error()&&actual==expected,"Callback identity");
 require(d.begin(f.bytes.data(),f.bytes.size()),"PWM begin");uint8_t pwm;size_t index=0;while(d.next(pwm)){
  int q14=(int(expected[index++])+1)>>1;int referencePwm=clip(128+floorPower(int64_t(q14)*130+8192,14),0,255);require(pwm==referencePwm,"PWM identity");}
 require(index==expected.size()&&!d.error(),"PWM length");
}
static void reject(std::vector<uint8_t> bytes){lbg1::Decoder d;if(d.begin(bytes.data(),bytes.size())){int16_t v;while(d.nextS16(v)){};}require(d.error()!=0,"Malformed input accepted");}
int main(){try{
 unsigned cases=0,invalid=0;
 for(int profile:{4,6})for(int n:{1,19,20,39,40,79,80,81,159,160,161,319,320,321,481,800})for(bool extras:{false,true}){
  auto f=make(n,profile,extras,0,2,0,0,0);check(f);++cases;
  auto bad=f.bytes;bad.pop_back();bad[11]=(bad.size()-13)&255;bad[12]=(bad.size()-13)>>8;reject(bad);++invalid;
  bad=f.bytes;bad.push_back(0);bad[11]=(bad.size()-13)&255;bad[12]=(bad.size()-13)>>8;reject(bad);++invalid;
 }
 for(int plan=0;plan<4;++plan)for(int code=0;code<7;++code){check(make(960,6,true,plan,code,code<5?3:0,1,1));++cases;}
 for(int sm=0;sm<4;++sm)for(int pm=0;pm<4;++pm){check(make(1280,6,true,3,1,2,sm,pm));++cases;}
 check(make(64000,4,false,1,2,0,1,1));++cases;
 for(int q=0;q<=3071;++q)require(lbg1::logToStep(q)==independentLog(q),"Shared integer log conversion");
 require(lbg1::logToStep(-1)==0&&lbg1::logToStep(3072)==0&&lbg1::logStart(0)==-1,"Scale endpoints");
 for(int kind=0;kind<7;++kind){Writer w;w.put(1,1);
  if(kind==0){w.put(1,1);w.put(0,2);w.put(7,3);} // reserved group
  else if(kind==1){w.put(1,1);w.put(3,2);w.put(10,4);} // group overshoot
  else if(kind==2){w.put(1,1);w.put(0,2);w.put(5,3);w.put(0x8000,16);} // coefficient rail
  else {w.put(0,1);w.put(kind==3?1:kind==4?2:0,2);
   if(kind==3){w.put(20,5);w.run(3);} // three runs for two blocks
   else if(kind==4){w.put(0,5);w.put(0,12);w.run(2);} // log silence
   else {w.put(20,5);w.put(2,2);w.put(kind==5?0:1,3);w.put(127,7);w.put(127,8);w.run(2);}}
  reject(header(w,320,6,false));++invalid;
 }
 auto f=make(320,4,false,0,0,0,0,0);Callback context{&f.bytes,13};lbg1::Decoder d;require(d.beginCallback(callback,&context,f.bytes.size()),"Failing body callback header");int16_t value;require(!d.nextS16(value)&&d.error()==lbg1::Decoder::READ_FAILURE,"Callback error");++invalid;
 std::cout<<"{\"valid_stream_cases\":"<<cases<<",\"invalid_cases\":"<<invalid<<",\"log_q8_values\":3072,\"passed\":true}\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
