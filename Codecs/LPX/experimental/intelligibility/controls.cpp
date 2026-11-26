#include "LpxAccuracy.h"
#include "LpxEncoder.h"
#include "LpxQuality.h"
#include "LpxFullBand.h"
#include <fstream>
#include <iterator>
#include <iostream>
#include <chrono>
#include <cmath>
#include <stdexcept>
#include <string>
using namespace lpx;
Pcm read(const char* path){std::ifstream f(path,std::ios::binary);std::vector<unsigned char>b{std::istreambuf_iterator<char>(f),{}};if(!f.eof()&&f.fail())throw std::runtime_error("read");if(b.empty()||b.size()%2)throw std::runtime_error("size");Pcm p(b.size()/2);for(size_t i=0;i<p.size();++i)p[i]=int16_t(unsigned(b[i*2])|(unsigned(b[i*2+1])<<8));return p;}
void bytes(const std::string&path,const std::vector<uint8_t>&b){std::ofstream f(path,std::ios::binary);f.write((const char*)b.data(),b.size());if(!f)throw std::runtime_error("write");}
void pcm(const std::string&path,const Pcm&p){std::vector<uint8_t>b;for(int v:p){b.push_back(uint16_t(v)&255);b.push_back(uint16_t(v)>>8);}bytes(path,b);}
void number(double x){if(std::isfinite(x))std::cout<<x;else std::cout<<"null";}
void pair(const double*x){std::cout<<'[';number(x[0]);std::cout<<',';number(x[1]);std::cout<<']';}
int main(int argc,char**argv){try{
 if(argc!=4)throw std::runtime_error("arguments");const auto ref=read(argv[1]);const std::string prefix=argv[2],mode=argv[3];Stream stream;AdaptiveReport report;if(!enc_reserve(ref.size()))throw std::runtime_error("reserve");auto start=std::chrono::steady_clock::now();
 if(mode=="4-nopre"){
  Stream context;context.accuracy=4;context.qualityTarget=QualityTarget::Pwm;SeedFitStatus status;
  stream=fitSeed(ref,4,8000,0,false,.97,&context,nullptr,&status,QualityTarget::Pwm);
  if(status!=SeedFitStatus::Success)throw std::runtime_error("seed failed");
 }else {int level=std::stoi(mode);stream=encodeAccuracy(ref,level,8000,report,mode=="3-full"?4:0,nullptr,QualityTarget::Pwm);if(report.error)throw std::runtime_error("accuracy failed");}
 const auto out=render(stream);if(stream.samples!=int(ref.size())||!verifyStream(stream,out))throw std::runtime_error("native mismatch");
 const double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();const auto packed=packV9(stream);bytes(prefix+".lpx",packed);pcm(prefix+".pcm",out);
 {std::ofstream f(prefix+".model");f<<stream.samples<<' '<<stream.profile<<' '<<stream.pre<<' '<<stream.bright<<' '<<stream.accuracy<<' '<<int(stream.qualityTarget)<<'\n';for(auto&v:stream.spectra){for(int x:v)f<<x<<' ';f<<'\n';}for(auto&v:stream.parameters){for(int x:v)f<<x<<' ';f<<'\n';}for(auto&v:stream.pulses)f<<v[0]<<' '<<v[1]<<'\n';for(auto&v:stream.extras)f<<v[0]<<' '<<v[1]<<'\n';}
 QualityContext quality(ref,true,8000,QualityTarget::Pwm);const auto m=quality.measure(out);FullBandContext full(ref,8000,QualityTarget::Pwm);const auto b=full.measure(out);int updates=0,extras=0;for(size_t i=0;i<stream.spectra.size();++i)updates+=!i||stream.spectra[i]!=stream.spectra[i-1];for(auto&v:stream.extras)extras+=v[1]!=0;
 std::cout.precision(17);std::cout<<"{\"mode\":\""<<mode<<"\",\"samples\":"<<stream.samples<<",\"bytes\":"<<packed.size()<<",\"pre\":"<<stream.pre<<",\"brightness\":"<<stream.bright<<",\"profile\":"<<stream.profile<<",\"spectral_updates\":"<<updates<<",\"active_extras\":"<<extras<<",\"seconds\":"<<seconds<<",\"pcm_sse\":"<<m.quality.error[0]<<",\"pwm_sse\":"<<m.quality.error[1]<<",\"stoi\":";pair(m.quality.stoi);std::cout<<",\"voice\":";pair(m.voice);std::cout<<",\"noise\":";pair(m.noise);std::cout<<",\"balanced_error\":";pair(b.balancedError);std::cout<<",\"balanced_temporal\":";pair(b.balancedTemporalError);std::cout<<",\"native_exact\":true,\"clipped\":"<<m.clipped<<"}\n";
 return 0;
}catch(const std::exception&e){std::cerr<<"Control failed: "<<e.what()<<'\n';return 1;}}
