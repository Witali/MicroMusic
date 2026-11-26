// Local research adapter. No changes to production formats or encoder policy.
#include "LpxAccuracy.h"
#include "LpxEncoder.h"
#include "LpxFullBand.h"
#include "Lpx4HybridCore.h"
#include <fstream>
#include <iostream>
#include <iterator>
#include <cmath>
#include <stdexcept>
using namespace lpx;
static std::vector<uint8_t> bytes(const char* p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("Cannot read input");return {std::istreambuf_iterator<char>(f),{}};}
static Pcm pcm(const char* p){auto b=bytes(p);if(b.size()%2)throw std::runtime_error("Odd PCM length");Pcm x;for(size_t i=0;i<b.size();i+=2)x.push_back(int16_t(b[i]|int(b[i+1])<<8));return x;}
static void save(const std::string& p,const std::vector<uint8_t>& b){std::ofstream f(p,std::ios::binary);f.write((const char*)b.data(),b.size());if(!f)throw std::runtime_error("Cannot write output");}
static void savePcm(const std::string& p,const Pcm& x){std::vector<uint8_t>b;for(auto v:x){b.push_back(v&255);b.push_back(uint16_t(v)>>8);}save(p,b);}
struct Reader{const std::vector<uint8_t>& b;size_t at=104;explicit Reader(const std::vector<uint8_t>& input):b(input){}int get(int n){int v=0;for(int i=0;i<n;i++,at++){if(at>=b.size()*8)throw std::runtime_error("Truncated packet");v|=((b[at/8]>>(at%8))&1)<<i;}return v;}int rice(int k,int w){int q=0;while(q<8&&!get(1))q++;return q==8?get(w):(q<<k)|get(k);}};
static Stream unpack(const std::vector<uint8_t>& b){
 if(b.size()<13||b[0]!='L'||b[1]!='9')throw std::runtime_error("Expected bounded V9");
 auto word=[&](int at){return int(b[at])|(int(b[at+1])<<8);};
 Stream s;s.profile=b[2]&127;s.samples=word(5);s.rate=word(3);s.pre=word(7);s.bright=word(9);
 if((s.profile!=4&&s.profile!=6)||int(b.size())!=13+word(11))throw std::runtime_error("Unsupported V9 packet");
 int count=(s.samples+319)/320,bits=s.profile==4?5:6;Reader r{b};
 s.spectra.resize(count);s.parameters.resize(count*2);s.pulses.resize(count*16);s.extras.assign(count*8,Pulse{{-1,0}});
 for(int f=0;f<count;f++){
  auto& v=s.spectra[f];if(r.get(1)){bool delta=r.get(1);if(delta&&!f)throw std::runtime_error("Initial delta");
   for(int k=0;k<10;k++){int z=r.rice(bits-4-int(delta),bits+int(delta));v[k]=delta?s.spectra[f-1][k]+(z&1?-z/2-1:z/2):(k?v[k-1]+1:0)+z;}
  }else {if(!f)throw std::runtime_error("Initial repeat");v=s.spectra[f-1];}
  for(int half=0;half<2;half++){
   int base=f*320+half*160;if(base>=s.samples)break;auto& p=s.parameters[f*2+half];p[0]=r.get(5);p[2]=r.get(3)*2;p[1]=p[2]?r.get(7)+18:18;
   for(int group=0;group<4&&base+group*40<s.samples;group++){
    auto& a=s.pulses[base/20+group*2];auto& c=s.pulses[base/20+group*2+1];
    if(s.profile==4){for(auto q:{&a,&c}){int pos=r.get(4);(*q)[0]=pos+(pos+2)/4;(*q)[1]=r.get(1)?8:-8;}}
    else {int low=r.get(4),high=r.get(5);a[0]=(high%5)*4+(low&3);c[0]=(high/5)*4+(low>>2);for(auto q:{&a,&c}){int amp=r.get(4);(*q)[1]=amp<8?amp:amp-16;}}
    if((b[2]&128)&&r.get(1)){auto& e=s.extras[base/40+group];e[0]=r.get(6);int amp=r.get(4);e[1]=amp<8?amp:amp-16;}
   }
  }
 }
 return s;
}
static Pcm native(const std::vector<uint8_t>& b){Lpx4HybridCore d;if(!d.begin(b.data(),b.size()))throw std::runtime_error("Decode begin failed");Pcm x;int16_t v;while(d.nextS16(v))x.push_back(v);if(d.error())throw std::runtime_error("Decode failed");return x;}
static void validateSpectra(const Stream& s){
 const int limit=s.profile==4?32:64;
 for(const auto& v:s.spectra)for(int k=0;k<10;k++)if(v[k]<0||v[k]>=limit||(k&&v[k]<=v[k-1]))throw std::runtime_error("Invalid spectral index range/order");
}
static void metrics(const Pcm& ref,const Pcm& out,const Stream* s=nullptr){
 if(ref.size()!=out.size())throw std::runtime_error("Length mismatch");
 QualityContext q(ref);auto m=q.quality(out);FullBandContext f(ref,8000);auto fm=f.measure(out);uint64_t energy=0;int clips=0;
 for(size_t i=0;i<ref.size();i++){int64_t v=ref[i];energy+=v*v;clips+=out[i]<=-32766||out[i]>=32766;}
 std::cout.precision(12);std::cout<<"{\"samples\":"<<ref.size()<<",\"pcm_sse\":"<<m.error[0]<<",\"pwm_sse\":"<<m.error[1]<<",\"pcm_stoi\":"<<m.stoi[0]<<",\"pwm_stoi\":"<<m.stoi[1]<<",\"ser_db\":"<<(m.error[0]?10*log10(double(energy)/m.error[0]):999)<<",\"spectral_error\":"<<fm.balancedError[0]<<",\"temporal_error\":"<<fm.balancedTemporalError[0]<<",\"clips\":"<<clips;
 if(s)std::cout<<",\"stable\":"<<(stableLpcStream(*s)?"true":"false")<<",\"level_safe\":"<<(safeSynthesisLevel(*s,ref,out)?"true":"false")<<",\"spectrum_safe\":"<<(safeSynthesisSpectrum(ref,out)?"true":"false");
 std::cout<<"}\n";
}
static void dump(const Stream& s,const std::string& prefix){
 std::ofstream f(prefix+".model");f<<s.samples<<' '<<s.profile<<' '<<s.pre<<' '<<s.bright<<'\n';
 for(auto& v:s.spectra){for(auto x:v)f<<x<<' ';f<<'\n';}for(auto& v:s.parameters){for(auto x:v)f<<x<<' ';f<<'\n';}
 for(auto& v:s.pulses)f<<v[0]<<' '<<v[1]<<'\n';for(auto& v:s.extras)f<<v[0]<<' '<<v[1]<<'\n';
}
int main(int argc,char** argv){try{
 if(argc<2)throw std::runtime_error("encode PCM prefix level calls | decode LPX PCM | measure sourcePCM candidatePCM | replace LPX bins sourcePCM prefix");
 std::string mode=argv[1];
 if(mode=="decode"&&argc==4){savePcm(argv[3],native(bytes(argv[2])));return 0;}
 if(mode=="measure"&&argc==4){metrics(pcm(argv[2]),pcm(argv[3]));return 0;}
 if(mode=="encode"&&argc==6){auto ref=pcm(argv[2]);if(!enc_reserve(ref.size()))throw std::runtime_error("Reserve failed");AdaptiveReport report;
  auto s=encodeAccuracy(ref,atoi(argv[4]),8000,report,atoi(argv[5]));if(report.error)throw std::runtime_error("Encode failed");
  auto b=packV9(s);auto out=render(s);if(native(b)!=out)throw std::runtime_error("Model/native mismatch");
  save(std::string(argv[3])+".lpx",b);savePcm(std::string(argv[3])+".pcm",out);dump(s,argv[3]);metrics(ref,out,&s);return 0;}
 if(mode=="replace"&&argc==6){auto b=bytes(argv[2]);auto original=native(b);auto s=unpack(b);validateSpectra(s);if(render(s)!=original)throw std::runtime_error("Unpack/native mismatch");
  std::ifstream f(argv[3]);for(auto& v:s.spectra)for(auto& x:v)if(!(f>>x))throw std::runtime_error("Missing spectral index");f>>std::ws;if(!f.eof())throw std::runtime_error("Trailing spectral data");
  validateSpectra(s);auto packed=packV9(s);auto out=render(s);if(native(packed)!=out)throw std::runtime_error("Repacked native mismatch");
  save(std::string(argv[5])+".lpx",packed);savePcm(std::string(argv[5])+".pcm",out);metrics(pcm(argv[4]),out,&s);return 0;}
 throw std::runtime_error("Invalid probe arguments");
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
