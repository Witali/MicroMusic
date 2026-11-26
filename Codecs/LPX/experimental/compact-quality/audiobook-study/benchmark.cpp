// Continuous Long study adapter. No production timer or decoder changes.
#include "LpxAccuracy.h"
#include "LpxEncoder.h"
#include "LpxCandidateEvaluation.h"
#include "LpxFullBand.h"
#include "LpxPitchGuard.h"
#include "Lpx4HybridCore.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <ctime>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <stdexcept>
#include <sstream>
using namespace lpx;
namespace {
void num(double value){if(std::isfinite(value))std::cout<<value;else std::cout<<"null";}
void pair(const double* values){std::cout<<'[';num(values[0]);std::cout<<',';num(values[1]);std::cout<<']';}
void boolval(bool value){std::cout<<(value?"true":"false");}
std::vector<uint8_t> readBytes(const char* path){std::ifstream f(path,std::ios::binary);if(!f)throw std::runtime_error("Cannot read input");return {std::istreambuf_iterator<char>(f),{}};}
Pcm readPcm(const char* path){const auto b=readBytes(path);if(b.size()%2)throw std::runtime_error("Odd PCM byte count");Pcm pcm(b.size()/2);for(size_t i=0;i<pcm.size();++i)pcm[i]=int16_t(uint16_t(b[2*i])|(uint16_t(b[2*i+1])<<8));return pcm;}
void save(const std::string& path,const std::vector<uint8_t>& data){std::ofstream f(path,std::ios::binary);f.write(reinterpret_cast<const char*>(data.data()),data.size());if(!f)throw std::runtime_error("Cannot write artifact");}
void savePcm(const std::string& path,const Pcm& pcm){std::vector<uint8_t> b; b.reserve(pcm.size()*2);for(int16_t x:pcm){b.push_back(uint16_t(x)&255);b.push_back(uint16_t(x)>>8);}save(path,b);}
uint32_t word(const std::vector<uint8_t>& b,size_t at,int width){if(at+width>b.size())throw std::runtime_error("Truncated header");uint32_t v=0;for(int i=0;i<width;++i)v|=uint32_t(b[at+i])<<(8*i);return v;}
struct Header {unsigned bytes;uint32_t samples,payload;bool wide,enhanced;};
Header header(const std::vector<uint8_t>& b,const Stream& s){
 if(b.size()<13||b[0]!='L'||b[1]!='9'||(b[2]&63)!=4)throw std::runtime_error("Expected P4 V9");
 Header h;h.wide=(b[2]&64)!=0;h.enhanced=(b[2]&128)!=0;h.bytes=h.wide?17:13;
 h.samples=word(b,5,h.wide?4:2);h.payload=word(b,h.wide?13:11,h.wide?4:2);
 if(h.samples!=uint32_t(s.samples)||h.wide!=(s.samples>64000)||word(b,3,2)!=8000
  ||word(b,h.wide?9:7,2)!=uint32_t(s.pre)||word(b,h.wide?11:9,2)!=uint32_t(s.bright)
  ||b.size()<h.bytes||h.payload!=b.size()-h.bytes)throw std::runtime_error("Long geometry mismatch");
 return h;
}
Pcm native(const std::vector<uint8_t>& bytes,const Stream& s){
 header(bytes,s);if(bytes.size()>std::numeric_limits<uint32_t>::max())throw std::runtime_error("Wide span overflow");
 Lpx4HybridCore receiver;if(!receiver.beginWideV9(bytes.data(),uint32_t(bytes.size())))throw std::runtime_error("Native beginWideV9 failed");
 Pcm output;output.reserve(s.samples);int16_t value;
 for(int i=0;i<s.samples;++i){if(!receiver.nextS16(value))throw std::runtime_error("Early native EOF");output.push_back(value);}
 if(receiver.nextS16(value)||receiver.error()||!receiver.finished())throw std::runtime_error("Native final EOF mismatch");
 return output;
}

void nativePwm(const std::vector<uint8_t>& bytes,const Stream& s,const Pcm& model) {
 Lpx4HybridCore receiver;if(!receiver.beginWideV9(bytes.data(),uint32_t(bytes.size())))throw std::runtime_error("PWM beginWideV9 failed");
 const auto mapped=pwm(model);uint8_t value;
 for(int i=0;i<s.samples;++i)if(!receiver.next(value)||int(mapped[i])!=(int(value)-128)*256)throw std::runtime_error("Native PWM mismatch");
 if(receiver.next(value)||receiver.error()||!receiver.finished())throw std::runtime_error("PWM EOF mismatch");
}
void validSavedModel(const Stream& s) {
 if(s.samples!=160000||s.profile!=4||s.rate!=8000||(s.accuracy!=3&&s.accuracy!=4)||s.qualityTarget!=QualityTarget::Pwm
  ||s.pre<0||s.pre>16384||s.bright<0||s.bright>11469)throw std::runtime_error("Invalid saved model geometry");
 for(const auto& v:s.spectra)for(int k=0;k<10;++k)if(v[k]<0||v[k]>31||(k&&v[k]<=v[k-1]))throw std::runtime_error("Invalid model LSF");
 for(const auto& v:s.parameters)if(v[0]<0||v[0]>31||v[1]<18||v[1]>145||v[2]<0||v[2]>14||(v[2]&1))throw std::runtime_error("Invalid model parameter");
 for(const auto& v:s.pulses)if(v[0]<0||v[0]>=20||(v[0]+3)%5==0||(v[1]!=-8&&v[1]!=8))throw std::runtime_error("Invalid model pulse");
 for(const auto& v:s.extras)if(v[1]<-8||v[1]>7||(v[1]&&(v[0]<0||v[0]>=40)))throw std::runtime_error("Invalid model extra");
}
Stream loadModel(const std::string& path) {
 std::ifstream f(path);std::string first;if(!f||!std::getline(f,first))throw std::runtime_error("Cannot read host model");
 std::istringstream line(first);Stream s;int target;
 if(!(line>>s.samples>>s.profile>>s.pre>>s.bright>>s.accuracy>>target))throw std::runtime_error("Invalid model header");
 line>>std::ws;if(!line.eof()||s.samples!=160000||s.profile!=4||target!=1)throw std::runtime_error("Wrong model schema");
 s.rate=8000;s.qualityTarget=QualityTarget::Pwm;
 s.spectra.resize(500);s.parameters.resize(1000);s.pulses.resize(8000);s.extras.resize(4000);
 for(auto& v:s.spectra)for(auto& x:v)if(!(f>>x))throw std::runtime_error("Missing model LSF");
 for(auto& v:s.parameters)for(auto& x:v)if(!(f>>x))throw std::runtime_error("Missing model parameter");
 for(auto& v:s.pulses)for(auto& x:v)if(!(f>>x))throw std::runtime_error("Missing model pulse");
 for(auto& v:s.extras)for(auto& x:v)if(!(f>>x))throw std::runtime_error("Missing model extra");
 f>>std::ws;if(!f.eof())throw std::runtime_error("Trailing model input");validSavedModel(s);return s;
}

struct Reader {const std::vector<uint8_t>& data;uint64_t at;Reader(const std::vector<uint8_t>& b,unsigned bytes):data(b),at(uint64_t(bytes)*8){}unsigned get(unsigned width){unsigned value=0;for(unsigned i=0;i<width;++i,++at){if(at>=uint64_t(data.size())*8)throw std::runtime_error("Truncated payload");value|=unsigned((data[at/8]>>(at%8))&1)<<i;}return value;}};
struct Bits {uint64_t headerBits=0,flags=0,modes=0,absolute=0,delta=0,scale=0,gain=0,lag=0,pulses=0,presence=0,extras=0,padding=0;int repeated=0,absoluteFrames=0,deltaFrames=0,escapes=0,zeroGain=0,activeExtras=0;};
Bits split(const std::vector<uint8_t>& bytes,const Stream& s){
 const auto h=header(bytes,s);Reader r(bytes,h.bytes);Bits x;x.headerBits=h.bytes*8;
 for(int f=0;f<(s.samples+319)/320;++f){++x.flags;if(r.get(1)){++x.modes;const bool delta=r.get(1);delta?++x.deltaFrames:++x.absoluteFrames;for(int k=0;k<10;++k){const auto begin=r.at;unsigned q=0;while(q<8&&!r.get(1))++q;if(q==8){r.get(5+delta);++x.escapes;}else r.get(1-delta);(delta?x.delta:x.absolute)+=r.at-begin;}}else ++x.repeated;
  for(int half=0;half<2;++half){int start=f*320+half*160;if(start>=s.samples)break;r.get(5);x.scale+=5;const unsigned gain=r.get(3);x.gain+=3;if(gain){r.get(7);x.lag+=7;}else ++x.zeroGain;
   for(int group=0;group<4&&start+group*40<s.samples;++group){r.get(10);x.pulses+=10;if(h.enhanced){++x.presence;if(r.get(1)){r.get(10);x.extras+=10;++x.activeExtras;}}}
  }
 }
 const uint64_t total=uint64_t(bytes.size())*8;if(r.at>total||total-r.at>7)throw std::runtime_error("Used-bit mismatch");x.padding=total-r.at;
 while(r.at<total)if(r.get(1))throw std::runtime_error("Nonzero final padding");
 if(x.headerBits+x.flags+x.modes+x.absolute+x.delta+x.scale+x.gain+x.lag+x.pulses+x.presence+x.extras+x.padding!=total)throw std::runtime_error("Packet accounting mismatch");
 return x;
}
void emitBits(const std::vector<uint8_t>& b,const Stream& s){const auto x=split(b,s);std::cout<<"{\"header\":"<<x.headerBits<<",\"spectral_repeat_flags\":"<<x.flags<<",\"spectral_mode_tags\":"<<x.modes<<",\"absolute_rice\":"<<x.absolute<<",\"delta_rice\":"<<x.delta<<",\"scale\":"<<x.scale<<",\"gain\":"<<x.gain<<",\"lag\":"<<x.lag<<",\"main_pulses\":"<<x.pulses<<",\"extra_presence\":"<<x.presence<<",\"extra_symbols\":"<<x.extras<<",\"padding\":"<<x.padding<<",\"spectral_total\":"<<x.flags+x.modes+x.absolute+x.delta<<",\"repeated_frames\":"<<x.repeated<<",\"absolute_frames\":"<<x.absoluteFrames<<",\"delta_frames\":"<<x.deltaFrames<<",\"rice_escapes\":"<<x.escapes<<",\"zero_gain_blocks\":"<<x.zeroGain<<",\"active_extras\":"<<x.activeExtras<<",\"total\":"<<uint64_t(b.size())*8<<'}';}
void emitGrid(const Stream& input){const auto s=canonicalAccuracy(input);int odd=0,updatedOdd=0,updates=0;for(size_t f=0;f<s.spectra.size();++f){const bool update=!f||s.spectra[f]!=s.spectra[f-1];updates+=update;for(int k=0;k<10;++k)if((s.spectra[f][k]-k)&1){++odd;updatedOdd+=update;}}std::cout<<"{\"odd_rank_residual_fields_all_frames\":"<<odd<<",\"odd_rank_residual_fields_updated_frames\":"<<updatedOdd<<",\"updated_frames\":"<<updates<<",\"held_frames\":"<<s.spectra.size()-updates<<'}';}
// The two diagnostic emitters below preserve the earlier studied equations.
void emitQuality(const Pcm& ref,const Pcm& out,const Stream& s){QualityContext q(ref,true,8000,QualityTarget::Pwm);FullBandContext f(ref,8000,QualityTarget::Pwm);const auto m=q.measure(out);const auto b=f.measure(out);std::cout<<"{\"pcm_sse\":"<<m.quality.error[0]<<",\"pwm_sse\":"<<m.quality.error[1]<<",\"stoi\":";pair(m.quality.stoi);std::cout<<",\"voice\":";pair(m.voice);std::cout<<",\"noise\":";pair(m.noise);std::cout<<",\"fullband_error\":";pair(b.balancedError);std::cout<<",\"fullband_temporal_error\":";pair(b.balancedTemporalError);std::cout<<",\"clipped\":"<<m.clipped<<",\"pitch_within\":["<<m.diagnostic[0].within<<','<<m.diagnostic[1].within<<"],\"pitch_collapsed\":["<<m.diagnostic[0].collapsed<<','<<m.diagnostic[1].collapsed<<"],\"period\":[";num(m.diagnostic[0].period);std::cout<<',';num(m.diagnostic[1].period);std::cout<<"],\"shape\":[";num(m.diagnostic[0].shape);std::cout<<',';num(m.diagnostic[1].shape);std::cout<<"],\"stable\":";boolval(stableLpcStream(s));std::cout<<",\"level_safe\":";boolval(safeSynthesisLevel(s,ref,out));std::cout<<",\"spectrum_safe\":";boolval(safeSynthesisSpectrum(ref,out));std::cout<<'}';}
void emitChanges(const Stream& a,const Stream& b){int indices=0,frames=0,scales=0,lags=0,gains=0,pos=0,amp=0,extras=0;for(size_t f=0;f<a.spectra.size();++f){frames+=a.spectra[f]!=b.spectra[f];for(int k=0;k<10;++k)indices+=a.spectra[f][k]!=b.spectra[f][k];}for(int i=0;i<(a.samples+159)/160;++i){scales+=a.parameters[i][0]!=b.parameters[i][0];lags+=a.parameters[i][1]!=b.parameters[i][1];gains+=a.parameters[i][2]!=b.parameters[i][2];}for(int i=0;i<2*((a.samples+39)/40);++i){pos+=a.pulses[i][0]!=b.pulses[i][0];amp+=a.pulses[i][1]!=b.pulses[i][1];}for(int i=0;i<(a.samples+39)/40;++i)extras+=a.extras[i]!=b.extras[i];std::cout<<"{\"spectral_frames\":"<<frames<<",\"spectral_indices\":"<<indices<<",\"scales\":"<<scales<<",\"lags\":"<<lags<<",\"gains\":"<<gains<<",\"pulse_positions\":"<<pos<<",\"pulse_amplitudes\":"<<amp<<",\"extras\":"<<extras<<",\"pre\":"<<(a.pre!=b.pre)<<",\"brightness\":"<<(a.bright!=b.bright)<<'}';}

void dump(const Stream& s,const std::string& prefix){std::ofstream f(prefix+".model");f<<s.samples<<' '<<s.profile<<' '<<s.pre<<' '<<s.bright<<' '<<s.accuracy<<' '<<int(s.qualityTarget)<<'\n';for(const auto& v:s.spectra){for(int x:v)f<<x<<' ';f<<'\n';}for(const auto& v:s.parameters){for(int x:v)f<<x<<' ';f<<'\n';}for(const auto& v:s.pulses)f<<v[0]<<' '<<v[1]<<'\n';for(const auto& v:s.extras)f<<v[0]<<' '<<v[1]<<'\n';if(!f)throw std::runtime_error("Cannot write model");}
void output(const Stream& s,const Pcm& reference,const std::string& prefix,bool writeArtifacts=true){const auto b=packV9(s);const auto pcm=render(s);const auto h=header(b,s);if(native(b,s)!=pcm)throw std::runtime_error("Independent native/model mismatch");nativePwm(b,s,pcm);split(b,s);if(writeArtifacts){save(prefix+".lpx",b);savePcm(prefix+".pcm",pcm);dump(s,prefix);}std::cout<<"{\"bytes\":"<<b.size()<<",\"header_bytes\":"<<h.bytes<<",\"long_header\":";boolval(h.wide);std::cout<<",\"declared_samples\":"<<h.samples<<",\"declared_payload_bytes\":"<<h.payload<<",\"host_accuracy\":"<<s.accuracy<<",\"produced_samples\":"<<pcm.size()<<",\"native_model_exact\":true,\"native_pcm_exact\":true,\"native_pwm_exact\":true,\"native_eof_exact\":true,\"grid\":";emitGrid(s);std::cout<<",\"bits\":";emitBits(b,s);std::cout<<",\"quality\":";emitQuality(reference,pcm,s);std::cout<<'}';}
void stage(const CompactEnsembleReport& r){std::cout<<"{\"enabled\":"<<r.enabled<<",\"eligible\":"<<r.eligible<<",\"attempted\":"<<r.attempted<<",\"search_calls\":"<<r.searchCalls<<",\"status\":"<<r.status<<",\"error\":"<<r.error<<",\"policy_budget_C\":"<<r.policyBudget<<",\"baseline_bytes_B0\":"<<r.baselineBytes<<",\"raw_bytes\":"<<r.rawBytes<<",\"selected_bytes\":"<<r.selectedBytes<<",\"raw_valid\":"<<r.rawValid<<",\"raw_changed\":"<<r.rawChanged<<",\"selected\":"<<r.selected<<",\"search_candidates\":"<<r.searchCandidates<<",\"search_selected\":"<<r.searchSelected<<",\"parameter_trials\":"<<r.parameterTrials<<",\"pulse_trials\":"<<r.pulseTrials<<",\"selection_candidates\":"<<r.selection.candidates<<",\"selection_accepted\":"<<r.selection.accepted<<",\"selection_error\":"<<r.selection.error<<",\"selection_octave_rejected\":"<<r.selection.octaveRejected<<",\"initial_objective\":";num(r.selection.initialObjective);std::cout<<",\"final_objective\":";num(r.selection.finalObjective);std::cout<<'}';}

void caseOutputs(const Stream& baseline,const Stream& raw,const Stream& selected,const Pcm& reference,const std::string& prefix,bool writeArtifacts,bool available) {
 const auto baselineBytes=packV9(baseline),selectedBytes=packV9(selected);
 if(selectedBytes.size()>baselineBytes.size())throw std::runtime_error("Selected output exceeds B0");
 const bool changed=selectedBytes!=baselineBytes;
 if(baseline.accuracy!=3||selected.accuracy!=(changed?4:3))throw std::runtime_error("Wrong stored host policy");
 ProfileQualityReport replay;const auto replayed=selectQualityProposals(baseline,reference,{&raw},replay,true,baselineBytes.size());
 if(replay.error||packV9(replayed)!=selectedBytes)throw std::runtime_error("Production selector replay mismatch");
 const auto a=render(baseline),b=render(raw),c=render(selected);
 FullBandContext bands(reference,8000,QualityTarget::Pwm);PitchGuardContext pitch(reference,a,8000,QualityTarget::Pwm);
 std::cout<<",\"baseline\":";output(baseline,reference,prefix+"-baseline",writeArtifacts);
 std::cout<<",\"raw_candidate\":";output(raw,reference,prefix+"-raw",writeArtifacts);
 std::cout<<",\"selected_output\":";output(selected,reference,prefix+"-selected",writeArtifacts);
 std::cout<<",\"raw_available\":";boolval(available);std::cout<<",\"raw_changed\":";boolval(packV9(raw)!=baselineBytes);std::cout<<",\"selected_changed\":";boolval(changed);
 std::cout<<",\"research_retention_guard_raw\":";boolval(bands.accepts(bands.measure(b),bands.measure(a)));std::cout<<",\"research_retention_guard_selected\":";boolval(bands.accepts(bands.measure(c),bands.measure(a)));
 std::cout<<",\"production_pitch_guard_raw\":";boolval(pitch.accepts(b));std::cout<<",\"production_pitch_guard_selected\":";boolval(pitch.accepts(c));
 std::cout<<",\"selector_replay_exact\":true,\"raw_changes\":";emitChanges(baseline,raw);std::cout<<",\"selected_changes\":";emitChanges(baseline,selected);
}
Stream loadOutput(const std::string& prefix,const Pcm& reference) {
 auto model=loadModel(prefix+".model");const auto data=readBytes((prefix+".lpx").c_str());const auto saved=readPcm((prefix+".pcm").c_str());
 if(packV9(model)!=data||saved.size()!=reference.size()||render(model)!=saved||native(data,model)!=saved)throw std::runtime_error("Saved byte/model/PCM mismatch");
 nativePwm(data,model,saved);split(data,model);return model;
}
void nativeMeta(const Stream& s) {
 const auto data=packV9(s);const auto h=header(data,s);
 std::cout<<"{\"native_pcm_exact\":true,\"native_pwm_exact\":true,\"native_eof_exact\":true,\"produced_samples\":"<<s.samples<<",\"declared_samples\":"<<h.samples<<",\"header_bytes\":"<<h.bytes<<'}';
}
int verifySaved(const char* source,const std::string& prefix) {
 const auto reference=readPcm(source);if(reference.size()!=160000)throw std::runtime_error("Wrong verification reference length");
 const auto baseline=loadOutput(prefix+"-baseline",reference),raw=loadOutput(prefix+"-raw",reference),selected=loadOutput(prefix+"-selected",reference);
 std::cout.precision(14);std::cout<<"{\"schema\":\"lpx-audiobook-p3-verify-v1\",\"model_schema\":\"lpx-audiobook-host-model-v1\",\"samples\":160000,\"rate\":8000,\"quality_target\":\"pwm\",\"no_encoding_or_search\":true,\"baseline_byte_ceiling_B0\":"<<packV9(baseline).size();
 caseOutputs(baseline,raw,selected,reference,prefix,false,raw.accuracy==4);std::cout<<",\"outputs\":{\"baseline\":";nativeMeta(baseline);std::cout<<",\"raw\":";nativeMeta(raw);std::cout<<",\"selected\":";nativeMeta(selected);std::cout<<"},\"passed\":true}\n";return 0;
}
}
#ifndef LPX_AUDIOBOOK_BENCHMARK_NO_MAIN
int main(int argc,char** argv){try{
 if(argc==4&&std::string(argv[1])=="--verify")return verifySaved(argv[2],argv[3]);
 if(argc!=3)throw std::runtime_error("SOURCE_PCM OUTPUT_PREFIX | --verify SOURCE_PCM OUTPUT_PREFIX");
 const auto reference=readPcm(argv[1]);const std::string prefix=argv[2];
 if(reference.size()!=160000||!enc_reserve(reference.size()))throw std::runtime_error("Expected one complete reserved 20-second target");
 const auto target=QualityTarget::Pwm;Stream resetPrefix;resetPrefix.qualityTarget=target;
 AdaptiveReport baselineReport;const auto begin=std::chrono::steady_clock::now();const auto cpu=std::clock();
 const auto baseline=encodeAccuracy(reference,3,8000,baselineReport,4,&resetPrefix,target);
 const double baselineWall=std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count();const double baselineCpu=double(std::clock()-cpu)/CLOCKS_PER_SEC;
 if(baselineReport.error||baseline.samples!=160000||baselineReport.compactEnsemble.searchCalls)throw std::runtime_error("Completed reset-prefix baseline failed");
 const auto baselineBytes=packV9(baseline);const int B0=baselineBytes.size();
 CompactEnsembleReport report;Stream raw;const auto next=std::chrono::steady_clock::now();const auto nextCpu=std::clock();
 CandidateEvaluation evaluation(reference,8000,true,target);
 const auto selected=refineCompactEnsemble(baseline,reference,report,&evaluation,&raw);
 const double helperWall=std::chrono::duration<double>(std::chrono::steady_clock::now()-next).count();const double helperCpu=double(std::clock()-nextCpu)/CLOCKS_PER_SEC;
 report.policyBudget=baselineReport.compactEnsemble.policyBudget;
 const bool available=raw.samples!=0;if(!available)raw=baseline;
 if(packV9(selected).size()>baselineBytes.size()||report.baselineBytes!=B0)throw std::runtime_error("Actual Long B0 mismatch");
 std::cout.precision(14);
 std::cout<<"{\"schema\":\"lpx-audiobook-p3-components-v1\",\"model_schema\":\"lpx-audiobook-host-model-v1\",\"samples\":160000,\"rate\":8000,\"quality_target\":\"pwm\",\"active_paths\":[\"pcm\",\"pwm\"],\"calls\":4,\"global_error\":"<<baselineReport.error<<",\"policy_budget_C\":"<<report.policyBudget<<",\"baseline_byte_ceiling_B0\":"<<B0<<",\"baseline_component_seconds\":"<<baselineWall<<",\"baseline_component_cpu_seconds\":"<<baselineCpu<<",\"optional_component_seconds\":"<<helperWall<<",\"optional_component_cpu_seconds\":"<<helperCpu<<",\"automatic_api_seconds\":null,\"legacy_cap\":"<<baselineReport.cap<<",\"legacy_selected\":"<<baselineReport.selected<<",\"legacy_candidates\":"<<baselineReport.candidates<<",\"legacy_stages\":"<<baselineReport.stages<<",\"baseline_optional_search_calls\":"<<baselineReport.compactEnsemble.searchCalls<<",\"stage\":";stage(report);
 caseOutputs(baseline,raw,selected,reference,prefix,true,available);std::cout<<"}\n";return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
#endif
