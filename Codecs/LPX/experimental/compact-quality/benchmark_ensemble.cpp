// Existing-encoder ensemble adapter. No production, decoder or search changes.
// Shared diagnostic functions below are copied from the frozen phase-1 adapter.
#define main prior_research_main
#include "../../research/lbg1-2026-11-26/probe.cpp"
#undef main
#include "LpxPitchGuard.h"
#include <chrono>
#include <ctime>
#include <sstream>
#include <limits>
namespace {
void num(double x){if(std::isfinite(x))std::cout<<x;else std::cout<<"null";}
void pair(const double* x){std::cout<<'[';num(x[0]);std::cout<<',';num(x[1]);std::cout<<']';}
void boolval(bool x){std::cout<<(x?"true":"false");}
struct Bits {uint64_t header=104,spectralFlags=0,spectralModes=0,absoluteRice=0,deltaRice=0,scales=0,gains=0,lags=0,mainPulses=0,presence=0,extras=0,padding=0;int repeats=0,absolute=0,delta=0,escapes=0,activeExtras=0,zeroGains=0;};
Bits split(const std::vector<uint8_t>& b,const Stream& s){Bits v;Reader r{b};const int bits=5;for(int f=0;f<int(s.spectra.size());++f){v.spectralFlags++;if(r.get(1)){v.spectralModes++;const bool delta=r.get(1);delta?++v.delta:++v.absolute;for(int k=0;k<10;++k){const auto start=r.at;int q=0;while(q<8&&!r.get(1))++q;if(q==8){r.get(bits+int(delta));++v.escapes;}else r.get(1-int(delta));(delta?v.deltaRice:v.absoluteRice)+=r.at-start;}}else ++v.repeats;for(int half=0;half<2;++half){const int base=f*320+half*160;if(base>=s.samples)break;r.get(5);v.scales+=5;const int gain=r.get(3);v.gains+=3;if(gain){r.get(7);v.lags+=7;}else ++v.zeroGains;for(int group=0;group<4&&base+group*40<s.samples;++group){r.get(10);v.mainPulses+=10;if(b[2]&128){v.presence++;if(r.get(1)){r.get(10);v.extras+=10;++v.activeExtras;}}}}}v.padding=b.size()*8-r.at;if(v.padding>7)throw std::runtime_error("Unexpected final padding");while(r.at<b.size()*8)if(r.get(1))throw std::runtime_error("Nonzero padding");const uint64_t total=v.header+v.spectralFlags+v.spectralModes+v.absoluteRice+v.deltaRice+v.scales+v.gains+v.lags+v.mainPulses+v.presence+v.extras+v.padding;if(total!=b.size()*8)throw std::runtime_error("Bit accounting mismatch");return v;}
void emitBits(const std::vector<uint8_t>& b,const Stream& s){const auto x=split(b,s);std::cout<<"{\"header\":"<<x.header<<",\"spectral_repeat_flags\":"<<x.spectralFlags<<",\"spectral_mode_tags\":"<<x.spectralModes<<",\"absolute_rice\":"<<x.absoluteRice<<",\"delta_rice\":"<<x.deltaRice<<",\"scale\":"<<x.scales<<",\"gain\":"<<x.gains<<",\"lag\":"<<x.lags<<",\"main_pulses\":"<<x.mainPulses<<",\"extra_presence\":"<<x.presence<<",\"extra_symbols\":"<<x.extras<<",\"padding\":"<<x.padding<<",\"spectral_total\":"<<x.spectralFlags+x.spectralModes+x.absoluteRice+x.deltaRice<<",\"repeated_frames\":"<<x.repeats<<",\"absolute_frames\":"<<x.absolute<<",\"delta_frames\":"<<x.delta<<",\"rice_escapes\":"<<x.escapes<<",\"zero_gain_blocks\":"<<x.zeroGains<<",\"active_extras\":"<<x.activeExtras<<",\"total\":"<<b.size()*8<<'}';}
void emitQuality(const Pcm& ref,const Pcm& out,const Stream& s){QualityContext q(ref,true,8000,QualityTarget::Pwm);FullBandContext f(ref,8000,QualityTarget::Pwm);const auto m=q.measure(out);const auto b=f.measure(out);std::cout<<"{\"pcm_sse\":"<<m.quality.error[0]<<",\"pwm_sse\":"<<m.quality.error[1]<<",\"stoi\":";pair(m.quality.stoi);std::cout<<",\"voice\":";pair(m.voice);std::cout<<",\"noise\":";pair(m.noise);std::cout<<",\"fullband_error\":";pair(b.balancedError);std::cout<<",\"fullband_temporal_error\":";pair(b.balancedTemporalError);std::cout<<",\"clipped\":"<<m.clipped<<",\"pitch_within\":["<<m.diagnostic[0].within<<','<<m.diagnostic[1].within<<"],\"pitch_collapsed\":["<<m.diagnostic[0].collapsed<<','<<m.diagnostic[1].collapsed<<"],\"period\":[";num(m.diagnostic[0].period);std::cout<<',';num(m.diagnostic[1].period);std::cout<<"],\"shape\":[";num(m.diagnostic[0].shape);std::cout<<',';num(m.diagnostic[1].shape);std::cout<<"],\"stable\":";boolval(stableLpcStream(s));std::cout<<",\"level_safe\":";boolval(safeSynthesisLevel(s,ref,out));std::cout<<",\"spectrum_safe\":";boolval(safeSynthesisSpectrum(ref,out));std::cout<<'}';}
void emitChanges(const Stream& a,const Stream& b){int indices=0,frames=0,scales=0,lags=0,gains=0,pos=0,amp=0,extras=0;for(size_t f=0;f<a.spectra.size();++f){frames+=a.spectra[f]!=b.spectra[f];for(int k=0;k<10;++k)indices+=a.spectra[f][k]!=b.spectra[f][k];}for(int i=0;i<(a.samples+159)/160;++i){scales+=a.parameters[i][0]!=b.parameters[i][0];lags+=a.parameters[i][1]!=b.parameters[i][1];gains+=a.parameters[i][2]!=b.parameters[i][2];}for(int i=0;i<2*((a.samples+39)/40);++i){pos+=a.pulses[i][0]!=b.pulses[i][0];amp+=a.pulses[i][1]!=b.pulses[i][1];}for(int i=0;i<(a.samples+39)/40;++i)extras+=a.extras[i]!=b.extras[i];std::cout<<"{\"spectral_frames\":"<<frames<<",\"spectral_indices\":"<<indices<<",\"scales\":"<<scales<<",\"lags\":"<<lags<<",\"gains\":"<<gains<<",\"pulse_positions\":"<<pos<<",\"pulse_amplitudes\":"<<amp<<",\"extras\":"<<extras<<",\"pre\":"<<(a.pre!=b.pre)<<",\"brightness\":"<<(a.bright!=b.bright)<<'}';}
}

#include "LpxBitrateProfiles.h"

namespace ensemble {
enum Rejection {
    Size=1, ActiveQuality=2, OldNoise=4, FullBand=8, Pitch=16,
    Clipping=32, Level=64, SpectrumSafety=128, Stability=256,
    CompleteSelector=512, Geometry=1024, Policy=2048
};

bool zeroState(const SynthesisState& s) {
    if(s.dd || s.cc)return false;
    for(int x:s.h)if(x)return false;
    for(int x:s.ring)if(x)return false;
    return true;
}

bool validModel(const Stream& s) {
    if(!validQualityTarget(s.qualityTarget) || (s.accuracy!=3 && s.accuracy!=4)
        || s.samples<1 || s.samples>64000 || s.rate!=8000 || s.profile!=4
        || s.pre<0 || s.pre>16384 || s.bright<0 || s.bright>11469
        || s.continuation || !zeroState(s.initial) || !s.lookahead.empty())return false;
    const int frames=(s.samples+319)/320;
    if(int(s.spectra.size())!=frames || int(s.parameters.size())<frames*2
        || int(s.pulses.size())<frames*16 || int(s.extras.size())<frames*8)return false;
    for(const auto& v:s.spectra)for(int k=0;k<10;++k)
        if(v[k]<0 || v[k]>31 || (k && v[k]<=v[k-1]))return false;
    for(int i=0;i<(s.samples+159)/160;++i) {
        const auto& v=s.parameters[i];
        if(v[0]<0 || v[0]>31 || v[1]<18 || v[1]>145
            || v[2]<0 || v[2]>14 || (v[2]&1))return false;
    }
    // The terminal 40-sample packet always contains both 20-sample pulses.
    for(int i=0;i<2*((s.samples+39)/40);++i) {
        const auto& v=s.pulses[i];
        if(v[0]<0 || v[0]>=20 || (v[0]+3)%5==0 || (v[1]!=-8 && v[1]!=8))return false;
    }
    for(int i=0;i<(s.samples+39)/40;++i) {
        const auto& v=s.extras[i];
        if(v[1]<-8 || v[1]>7 || (v[1] && (v[0]<0 || v[0]>=40)))return false;
    }
    return true;
}

Stream checked(const std::vector<uint8_t>& blob,QualityTarget target,int accuracy) {
    if(!validQualityTarget(target) || (accuracy!=3 && accuracy!=4))
        throw std::runtime_error("Invalid checker policy");
    // Parse using the native bounded receiver first; check explicit EOF below.
    const auto decoded=native(blob);
    auto s=unpack(blob);s.accuracy=accuracy;s.qualityTarget=target;
    if(!validModel(s) || decoded.size()!=size_t(s.samples)
        || render(s)!=decoded || packV9(s)!=blob)
        throw std::runtime_error("Policy/native/serialization mismatch");
    Lpx4HybridCore receiver;
    if(!receiver.begin(blob.data(),blob.size()))throw std::runtime_error("Native begin");
    int16_t value;for(int expected:decoded)
        if(!receiver.nextS16(value) || value!=expected)throw std::runtime_error("Native sample");
    if(receiver.nextS16(value) || receiver.error() || !receiver.finished())
        throw std::runtime_error("Native EOF");
    split(blob,s); // Includes exact used-bit accounting and zero final padding.
    return s;
}

bool samePhysical(const Stream& a,const Stream& b) {
    return a.qualityTarget==b.qualityTarget && a.samples==b.samples && a.rate==b.rate
        && a.profile==b.profile && a.pre==b.pre && a.bright==b.bright
        && a.spectra==b.spectra && a.parameters==b.parameters
        && a.pulses==b.pulses && a.extras==b.extras
        && a.continuation==b.continuation && a.allowExtras==b.allowExtras
        && a.previousSpectrum==b.previousSpectrum && a.previousInput==b.previousInput
        && a.previousCoefficients==b.previousCoefficients && a.lookahead==b.lookahead
        && zeroState(a.initial) && zeroState(b.initial);
}

Stream relabelFine(const Stream& baseline) {
    if(baseline.accuracy!=3 || !validModel(baseline))
        throw std::runtime_error("Expected original P3 baseline");
    Stream fine=baseline;fine.accuracy=4;
    const auto original=packV9(baseline),relabelled=packV9(fine);
    if(!samePhysical(baseline,fine) || original!=relabelled
        || render(baseline)!=render(fine) || native(original)!=render(fine))
        throw std::runtime_error("Host relabel changed physical output");
    return fine;
}

struct SearchResult {
    Stream raw;
    BitrateReport report;
    bool fallback=false;
    std::string fallbackReason="none";
    double seconds=0,cpuSeconds=0;
};

void settleSearch(const Stream& baselineFine,const Stream& proposed,
                  const BitrateReport& report,SearchResult& result) {
    if(baselineFine.accuracy!=4 || !validModel(baselineFine))
        throw std::runtime_error("Invalid fine incumbent");
    result.report=report;result.raw=baselineFine;
    result.fallback=true;
    if(report.error){result.fallbackReason="search_error";return;}
    if(proposed.accuracy!=4 || proposed.qualityTarget!=baselineFine.qualityTarget) {
        result.fallbackReason="result_policy";return;
    }
    if(!validModel(proposed) || proposed.samples!=baselineFine.samples
        || proposed.rate!=baselineFine.rate || proposed.profile!=baselineFine.profile) {
        result.fallbackReason="result_geometry";return;
    }
    try {
        const auto blob=packV9(proposed);
        if(blob.size()>packV9(baselineFine).size()) {
            result.fallbackReason="result_above_B0";return;
        }
        checked(blob,proposed.qualityTarget,4);
        if(native(blob)!=render(proposed)) {
            result.fallbackReason="result_native_mismatch";return;
        }
        result.raw=proposed;result.fallback=false;result.fallbackReason="none";
    }catch(const std::exception&) { result.fallbackReason="result_malformed"; }
}

SearchResult runExisting(const Pcm& reference,const Stream& baseline) {
    if(reference.size()!=size_t(baseline.samples))throw std::runtime_error("Source geometry");
    const auto incumbentFine=relabelFine(baseline),prefixFine=relabelFine(baseline);
    if(!samePhysical(incumbentFine,prefixFine))throw std::runtime_error("Copies differ");
    const int B0=packV9(baseline).size();
    SearchResult result;BitrateReport report;Stream proposed;
    const auto start=std::chrono::steady_clock::now();const auto cpu=std::clock();
    try {
        // Exactly one existing encoder invocation; no added search/refinement.
        proposed=encodeThreeK(reference,B0,report,.97,&incumbentFine,&prefixFine,baseline.qualityTarget);
    }catch(const std::exception&) {report.error=-1000;}
    result.seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
    result.cpuSeconds=double(std::clock()-cpu)/CLOCKS_PER_SEC;
    settleSearch(incumbentFine,proposed,report,result);
    return result;
}

struct Protection {
    unsigned reject=0;
    bool changed=false,admitted=false,selector=false;
    Stream selected;
};

Protection protect(const Pcm& reference,const Stream& baseline,const Stream& candidate) {
    if(baseline.accuracy!=3 || !validModel(baseline)
        || reference.size()!=size_t(baseline.samples))throw std::runtime_error("Protection baseline");
    Protection result;result.selected=baseline;
    if(candidate.accuracy!=4 || candidate.qualityTarget!=baseline.qualityTarget) {
        result.reject|=Policy;return result;
    }
    if(!validModel(candidate) || candidate.samples!=baseline.samples
        || candidate.rate!=baseline.rate || candidate.profile!=baseline.profile) {
        result.reject|=Geometry;return result;
    }
    const auto ab=packV9(baseline),bb=packV9(candidate);
    const auto ap=render(baseline),bp=render(candidate);
    if(native(ab)!=ap || native(bb)!=bp) {result.reject|=Geometry;return result;}
    result.changed=ab!=bb;
    QualityContext quality(reference,true,8000,baseline.qualityTarget);
    FullBandContext full(reference,8000,baseline.qualityTarget);
    PitchGuardContext pitch(reference,ap,8000,baseline.qualityTarget);
    const auto a=quality.measure(ap),b=quality.measure(bp);
    if(bb.size()>ab.size())result.reject|=Size;
    if(!noRegression(b.quality,a.quality))result.reject|=ActiveQuality;
    for(int path=0;path<qualityPathCount(baseline.qualityTarget);++path)
        if(!std::isfinite(b.noise[path]) || b.noise[path]>a.noise[path]+1e-12)result.reject|=OldNoise;
    if(!full.accepts(full.measure(bp),full.measure(ap)))result.reject|=FullBand;
    if(!pitch.accepts(bp))result.reject|=Pitch;
    if(b.clipped>a.clipped)result.reject|=Clipping;
    if(!safeSynthesisLevel(candidate,reference,bp))result.reject|=Level;
    if(!safeSynthesisSpectrum(reference,bp))result.reject|=SpectrumSafety;
    if(!stableLpcStream(candidate))result.reject|=Stability;
    ProfileQualityReport selection;
    const auto chosen=selectQualityProposals(baseline,reference,{&candidate},selection,true,ab.size());
    if(selection.error)throw std::runtime_error("Complete selector error");
    result.selector=bb!=ab && packV9(chosen)==bb;
    if(result.changed && !result.selector)result.reject|=CompleteSelector;
    result.admitted=result.changed && !result.reject;
    if(result.admitted)result.selected=candidate;
    return result;
}

void emitGrid(const Stream& s) {
    int odd=0,updatedOdd=0,changed=0;
    for(size_t f=0;f<s.spectra.size();++f) {
        const bool update=!f || s.spectra[f]!=s.spectra[f-1];changed+=update;
        for(int k=0;k<10;++k)if((s.spectra[f][k]-k)&1) {++odd;updatedOdd+=update;}
    }
    std::cout<<"{\"odd_rank_residual_fields_all_frames\":"<<odd
        <<",\"odd_rank_residual_fields_updated_frames\":"<<updatedOdd
        <<",\"updated_frames\":"<<changed<<",\"held_frames\":"<<s.spectra.size()-changed<<'}';
}

void emitOutput(const Stream& s,const Pcm& reference,const std::string& prefix) {
    const auto blob=packV9(s);const auto out=render(s);
    checked(blob,s.qualityTarget,s.accuracy);
    if(native(blob)!=out)throw std::runtime_error("Output model/native mismatch");
    save(prefix+".lpx",blob);savePcm(prefix+".pcm",out);dump(s,prefix);
    std::cout<<"{\"bytes\":"<<blob.size()<<",\"host_accuracy\":"<<s.accuracy
        <<",\"native_model_exact\":true,\"reserialize_exact\":true,\"grid\":";
    emitGrid(s);std::cout<<",\"bits\":";emitBits(blob,s);
    std::cout<<",\"quality\":";emitQuality(reference,out,s);std::cout<<'}';
}
} // namespace ensemble

#ifndef LPX_ENSEMBLE_NO_MAIN
int main(int argc,char** argv) {
    try {
        if(argc!=6)throw std::runtime_error("SOURCE BASELINE_LPX OUTPUT_PREFIX pcm|pwm POLICY_C");
        const auto reference=pcm(argv[1]);const auto original=bytes(argv[2]);
        const std::string prefix=argv[3],mode=argv[4];
        if(mode!="pcm" && mode!="pwm")throw std::runtime_error("Invalid target");
        const auto target=mode=="pcm"?QualityTarget::Pcm:QualityTarget::Pwm;
        const int C=std::stoi(argv[5]);
        auto baseline=ensemble::checked(original,target,3);
        if(reference.size()!=size_t(baseline.samples) || C<int(original.size())
            || !enc_reserve(reference.size()))throw std::runtime_error("Invalid reference/budget/reserve");
        const auto search=ensemble::runExisting(reference,baseline);
        const auto protection=ensemble::protect(reference,baseline,search.raw);
        std::cout.precision(14);
        std::cout<<"{\"samples\":"<<reference.size()<<",\"rate\":8000,\"target\":\""<<mode
            <<"\",\"baseline_byte_ceiling_B0\":"<<original.size()<<",\"policy_budget_C\":"<<C
            <<",\"search_calls\":1,\"bandwidth_argument\":0.97,\"physical_relabel_exact\":true"
            <<",\"encode_seconds\":"<<search.seconds<<",\"encode_cpu_seconds\":"<<search.cpuSeconds
            <<",\"search_fallback\":";boolval(search.fallback);
        std::cout<<",\"fallback_reason\":\""<<search.fallbackReason<<"\",\"search\":{\"error\":"<<search.report.error
            <<",\"candidates\":"<<search.report.candidates<<",\"selected\":"<<search.report.selected
            <<",\"parameter_trials\":"<<search.report.parameterTrials<<",\"pulse_trials\":"<<search.report.pulseTrials<<'}';
        std::cout<<",\"baseline_grid\":";ensemble::emitGrid(baseline);
        std::cout<<",\"raw-ensemble\":";ensemble::emitOutput(search.raw,reference,prefix+"-raw");
        std::cout<<",\"protected\":";ensemble::emitOutput(protection.selected,reference,prefix+"-protected");
        std::cout<<",\"protection\":{\"raw_changed\":";boolval(protection.changed);
        std::cout<<",\"protected_ensemble_selected\":";boolval(protection.admitted);
        std::cout<<",\"existing_selector_chose_ensemble\":";boolval(protection.selector);
        std::cout<<",\"rejection_bits\":"<<protection.reject<<",\"raw_size_delta\":"
            <<int64_t(packV9(search.raw).size())-int64_t(original.size())<<",\"raw_changes\":";
        emitChanges(baseline,search.raw);std::cout<<",\"protected_changes\":";
        emitChanges(baseline,protection.selected);std::cout<<"}}\n";
        return 0;
    }catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
#endif
