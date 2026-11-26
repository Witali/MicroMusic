// Strict Z80 opcode subset, immutable ROM. Aborts on any unhandled opcode.
#include <array>
#include <vector>
#include <fstream>
#include <iostream>
#include <cstdint>
#include <stdexcept>
#include <iterator>
#include <sstream>
using namespace std;
vector<uint8_t> read(const char*p){ifstream f(p,ios::binary);return vector<uint8_t>(istreambuf_iterator<char>(f),{});}
struct CPU{
 const vector<uint8_t> m; array<uint8_t,8> r{},q{}; uint8_t f=0,fa=0,aa=0,ireg=0;uint16_t pc=0,sp=0,ix=0,iy=0;uint64_t t=0,steps=0;bool z(){return f&64;}void setz(uint8_t a){f=(f&~64)|(a?0:64);}uint8_t next(){return m.at(pc++);}uint16_t word(){uint16_t a=next();return a|(uint16_t(next())<<8);}uint16_t rp(int i){return uint16_t(r[2*i])*256+r[2*i+1];}void rp(int i,uint16_t n){r[2*i]=n>>8;r[2*i+1]=n;}uint8_t val(int i){return i==6?m.at(rp(2)):r[i];}void put(int i,uint8_t v){if(i==6)throw runtime_error("write to RAM");r[i]=v;}
 int edge=-1;uint8_t port=0,high=255;CPU(vector<uint8_t> mm,uint8_t p,uint8_t h):m(move(mm)),port(p),high(h){}
 void step(){uint16_t old=pc;uint8_t op=next();unsigned n=0;edge=-1;
  if(op==0||op==0xf3)n=4;
  else if(op==0x37){f|=1;n=4;}
  else if(op==0x08){swap(r[7],aa);swap(f,fa);n=4;}
  else if(op==0xd9){for(int i=0;i<6;i++)swap(r[i],q[i]);n=4;}
  else if(op==0xdd||op==0xfd){auto &x=op==0xdd?ix:iy;auto sub=next();if(sub==0x21){x=word();n=14;}else if(sub==0x7e){int8_t d=next();r[7]=m.at(uint16_t(x+d));n=19;}else if(sub==0x23){x++;n=10;}else if(sub==0xb4){r[7]|=x>>8;f&=~1;setz(r[7]);n=8;}else if(sub==0x85){unsigned v=r[7]+(x&255);r[7]=v;f=(f&~1)|(v>>8);setz(r[7]);n=8;}else if((sub&0xc0)==0x40&&sub!=0x76){int d=(sub>>3)&7,s=sub&7;if(d==6||s==6)throw runtime_error("indexed memory op");uint8_t v=s==4?x>>8:s==5?x&255:r[s];if(d==4)x=(x&255)|(uint16_t(v)<<8);else if(d==5)x=(x&0xff00)|v;else r[d]=v;n=8;}else throw runtime_error("index opcode");}
  else if(op==0xcb){auto sub=next();if(sub==0xfd)r[5]|=128;else if(sub==0x3c){auto v=r[4];r[4]=v>>1;f=(f&~1)|(v&1);setz(r[4]);}else if(sub==0x1d){auto v=r[5];r[5]=(v>>1)|((f&1)<<7);f=(f&~1)|(v&1);setz(r[5]);}else if(sub==0x42||sub==0x4a||sub==0x52){setz(r[2]&(1<<((sub-0x42)/8)));}else throw runtime_error("CB opcode");n=8;}
  else if(op==0xed){auto sub=next();if(sub==0x44){uint8_t v=r[7];r[7]=uint8_t(0-v);f=(f&~1)|(v!=0);setz(r[7]);n=8;}else if(sub==0x42){int v=int(rp(2))-int(rp(0))-(f&1);rp(2,uint16_t(v));f=(f&~1)|(v<0);n=15;}else if(sub==0x4f){n=9;}else if(sub==0x47){ireg=r[7];n=9;}else if(sub==0x57){r[7]=ireg;setz(r[7]);n=9;}else{if(sub!=0x41&&sub!=0x49)throw runtime_error("ED opcode");if(r[1]!=port||r[0]!=high)throw runtime_error("port/BC corruption");edge=sub==0x41?1:0;n=12;}}
  else if(op==0x31){sp=word();n=10;}
  else if(op==0x33){sp++;n=6;}
  else if(op==0x3b){sp--;n=6;}
  else if((op&0xcf)==1){int i=(op>>4)&3;if(i==3)throw runtime_error("SP opcode");rp(i,word());n=10;}
  else if(op==0x03||op==0x0b){rp(0,rp(0)+(op==3?1:-1));n=6;}
  else if(op==0x0a){r[7]=m.at(rp(0));n=7;}
  else if(op==0x0f||op==0x07){auto v=r[7];r[7]=op==0x0f?((v>>1)|(v<<7)):((v<<1)|(v>>7));f=(f&~1)|((op==0x0f?v:v>>7)&1);n=4;}
  else if(op==0x3c){r[7]++;setz(r[7]);n=4;}
  else if(op==0x2c){r[5]++;setz(r[5]);n=4;}
  else if(op==0xe6){r[7]&=next();f&=~1;setz(r[7]);n=7;}
  else if(op==0x83||op==0x84||op==0x87){unsigned v=r[7]+r[op&7];r[7]=v;f=(f&~1)|(v>>8);setz(r[7]);n=4;}
  else if(op==0x8e){unsigned v=r[7]+val(6)+(f&1);r[7]=v;f=(f&~1)|(v>>8);setz(r[7]);n=7;}
  else if(op==0xce){unsigned v=r[7]+next()+(f&1);r[7]=v;f=(f&~1)|(v>>8);setz(r[7]);n=7;}
  else if(op==0xf6){r[7]|=next();f&=~1;setz(r[7]);n=7;}
  else if(op==0xb2||op==0xb3){r[7]|=r[op&7];f&=~1;setz(r[7]);n=4;}
  else if(op==0x3d){r[7]--;setz(r[7]);n=4;}
  else if(op==0x23||op==0x2b){rp(2,rp(2)+(op==0x23?1:-1));n=6;}
  else if(op==0x24){r[4]++;setz(r[4]);n=4;}
  else if((op&0xc7)==6){put((op>>3)&7,next());n=7;}
  else if(op>=0x40&&op<=0x7f&&op!=0x76){int d=(op>>3)&7,s=op&7;put(d,val(s));n=s==6?7:4;}
  else if(op==0x86){r[7]+=val(6);setz(r[7]);n=7;}
  else if(op==0xb7){f&=~1;setz(r[7]);n=4;}
  else if(op==0xbf){f&=~1;setz(0);n=4;}
  else if(op==0x1f){auto v=r[7];r[7]=(v>>1)|((f&1)<<7);f=(f&~1)|(v&1);n=4;}
  else if(op==0xaf){r[7]=0;setz(0);n=4;}
  else if(op==0xd6){auto a=next();uint8_t v=r[7];r[7]=v-a;f=(f&~1)|(v<a);setz(r[7]);n=7;}
  else if(op==0xfe){auto a=next();f=(f&~1)|(r[7]<a);setz(r[7]-a);n=7;}
  else if(op==0x9f){unsigned v=f&1;r[7]=uint8_t(0-v);f=(f&~1)|v;setz(r[7]);n=4;}
  else if(op==0xde){unsigned a=next()+(f&1);unsigned v=r[7];f=(f&~1)|(v<a);r[7]=uint8_t(v-a);setz(r[7]);n=7;}
  else if(op==0xc3||op==0xca||op==0xc2||op==0xda||op==0xd2){auto x=word();if(op==0xc3||(op==0xca&&z())||(op==0xc2&&!z())||(op==0xda&&(f&1))||(op==0xd2&&!(f&1)))pc=x;n=10;}
  else if(op==0x10){int8_t d=next();r[0]--;if(r[0]){pc+=d;n=13;}else n=8;}
  else if(op==0x18||op==0x20||op==0x28){int8_t d=next();if(op==0x18||(op==0x20&&!z())||(op==0x28&&z())){pc+=d;n=12;}else n=7;}
  else if(op==0xe9){pc=rp(2);n=4;}
  else if(op==0xe1){uint16_t lo=m.at(sp++);uint16_t hi=m.at(sp++);rp(2,lo|(hi<<8));n=10;}
  else if(op==0x29){rp(2,rp(2)*2);n=11;}
  else if(op==0xc6){unsigned v=r[7]+next();r[7]=v;f=(f&~1)|(v>>8);setz(r[7]);n=7;}
  else if(op==0xb5){r[7]|=r[5];setz(r[7]);n=4;}
  else if(op==0xc9){uint16_t lo=m.at(sp++);uint16_t hi=m.at(sp++);pc=lo|(hi<<8);n=10;}
  else if(op==0xeb){swap(r[2],r[4]);swap(r[3],r[5]);n=4;}
  else if(op==0x19){rp(2,rp(2)+rp(1));n=11;}
  else if(op==0x39){rp(2,rp(2)+sp);n=11;}
  else if(op==0xf9){sp=rp(2);n=6;}
  else {ostringstream s;s<<"unsupported opcode "<<hex<<int(op)<<" at "<<old;throw runtime_error(s.str());}
  t+=n;steps++;
 }
};
int main(int argc,char**argv){try{
 if(argc!=3)throw runtime_error("usage: test_pwm ROM.bin expected.widths");
 auto rom=read(argv[1]);auto exp=read(argv[2]);if(rom.size()!=65536||exp.size()%16)throw runtime_error("bad inputs");CPU c(rom,0,16);
 uint64_t start=0,edges=0;size_t np=exp.size()/2;vector<bool> covered(65536);int coverage=0;uint16_t before;
 while(edges<2*np+1){before=c.pc;c.step();if(c.edge>=0){
  if(edges==0)start=c.t;
  if(c.edge!=int(edges%2==0))throw runtime_error("edge polarity");
  size_t j=edges/2;uint64_t want=start+j*320;
  if(edges%2){if(j>=np)throw runtime_error("unexpected low edge");want+=exp[j*2]+256*exp[j*2+1];}
  if(c.t!=want){ostringstream ss;ss<<"timing failure at edge "<<edges<<" actual "<<c.t<<" expected "<<want<<" PC "<<hex<<before;throw runtime_error(ss.str());}
  if(!(edges%2)&&!covered[before]){covered[before]=true;coverage++;}edges++;
 }
 if(c.steps>1000000000)throw runtime_error("runaway");}
 cout<<"{\"samples\":"<<np/8<<",\"periods\":"<<np<<",\"io_writes\":"<<edges<<",\"memory_writes\":0,\"cycles_per_sample\":2560,\"cycles_per_period\":320,\"pulse_routines_exercised\":"<<coverage<<",\"instructions\":"<<c.steps<<",\"cycles\":"<<c.t<<"}\n";
 return 0;}catch(exception&e){cerr<<e.what()<<"\n";return 1;}}
