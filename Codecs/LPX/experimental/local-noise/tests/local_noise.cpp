// Independent numerical/search contracts for the prospective local-noise score.
#include "LocalNoise.h"
#include "LpxQuality.h"
#include "LpxFullBand.h"
#include "LpxAdaptiveController.h"
#include "Lpx4HybridCore.h"
#include <algorithm>
#include <cmath>
#include <complex>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

namespace {
using namespace lpx;
constexpr double pi=3.14159265358979323846;
int contracts=0;
void need(bool condition,const char* message) {
    ++contracts;if(!condition){std::fprintf(stderr,"FAIL: %s\n",message);std::exit(1);}
}
bool sameNumber(double a,double b) { return a==b||(std::isnan(a)&&std::isnan(b)); }
void close(double actual,double expected,double tolerance,const char* message) {
    need(std::isfinite(actual)&&std::isfinite(expected)&&std::abs(actual-expected)<=tolerance*std::max(1.,std::abs(expected)),message);
}
Pcm tone(int n,int rate,double amplitude,double frequency) {
    Pcm result(n);for(int i=0;i<n;++i)result[i]=int16_t(std::nearbyint(amplitude*std::sin(2*pi*frequency*i/rate)));return result;
}
Pcm perturbed(const Pcm& source,int rate,double amplitude,double frequency) {
    Pcm result=source;for(int i=0;i<int(result.size());++i)
        result[i]=int16_t(std::nearbyint(source[i]+amplitude*std::sin(2*pi*frequency*i/rate)));return result;
}
Pcm manualPwm(const Pcm& source) {
    Pcm result;for(int value:source) {
        int q14=(value+1)>>1,duty=std::max(0,std::min(255,128+((q14*130+8192)>>14)));
        result.push_back(int16_t((duty-128)*256));
    }return result;
}
bool sameAnalysis(const std::vector<LocalNoiseWindow>& a,const std::vector<LocalNoiseWindow>& b) {
    if(a.size()!=b.size())return false;
    for(size_t i=0;i<a.size();++i) {
        const auto& x=a[i];const auto& y=b[i];
        if(x.start!=y.start||x.supported!=y.supported||x.quiet!=y.quiet||x.transient!=y.transient||x.voiced!=y.voiced
           ||!sameNumber(x.period,y.period)||x.periodicity!=y.periodicity||x.harmonicFraction!=y.harmonicFraction
           ||x.normalization!=y.normalization||x.interharmonic!=y.interharmonic||x.sourceMagnitude!=y.sourceMagnitude)return false;
    }return true;
}
// Direct O(N^2) DFT, independent of production periodogram/FFT code. This is
// the defining real Hann transform, not a translation of its radix algorithm.
std::array<double,257> magnitudes(const Pcm& samples,int start) {
    std::array<double,257> result={};double input[512];
    for(int i=0;i<512;++i)input[i]=start+i>=0&&start+i<int(samples.size())?
        samples[start+i]*(.5-.5*std::cos(2*pi*i/511)):0.;
    for(int k=0;k<=256;++k) {
        std::complex<double> value(0,0);
        for(int j=0;j<512;++j)value+=input[j]*std::complex<double>(std::cos(2*pi*k*j/512),-std::sin(2*pi*k*j/512));
        result[k]=std::abs(value);
    }return result;
}
void metric() {
    const int rate=8000;
    const auto source=tone(4096,rate,4000,200);
    const auto harmonic=perturbed(source,rate,1000,400),interharmonic=perturbed(source,rate,1000,500);
    const auto lowerSseNoise=perturbed(source,rate,800,500);
    LocalNoiseContext context(source,rate,QualityTarget::Pcm);
    const auto frozen=context.analysis();
    const auto clean=context.measure(source),h=context.measure(harmonic),off=context.measure(interharmonic),trade=context.measure(lowerSseNoise);
    need(clean.valid&&clean.voicedWindows>0,"known periodic source was not eligible for voiced analysis");
    close(clean.score,0,1e-14,"exact source has nonzero PCM loss");
    const auto hSse=sse(source,harmonic),nSse=sse(source,interharmonic);
    need(std::abs(double(hSse)-double(nSse))/std::max(hSse,nSse)<.003,"equal-energy perturbations did not have comparable SSE");
    need(off.interharmonic[0]>h.interharmonic[0]&&off.score>h.score,"equal-SSE interharmonic corruption was not ranked worse");
    need(sse(source,lowerSseNoise)<hSse&&trade.magnitude[0]<h.magnitude[0],"tradeoff fixture did not improve SSE/magnitude");
    need(trade.score>h.score,"new objective could not express a prospective local SSE/noise tradeoff");
    need(std::isnan(off.magnitude[1])&&std::isnan(off.interharmonic[1]),"PCM target computed an inactive PWM score");
    need(sameAnalysis(frozen,context.analysis()),"candidate scoring moved the source mask or normalization");
    for(const auto& window:frozen) {
        need(window.interharmonic[0]==0,"DC is labelled interharmonic noise");
        if(window.voiced) {
            need(window.supported&&!window.quiet&&!window.transient,"unsupported or fallback window received voiced weighting");
            need(std::abs(1200*std::log2(window.period/(rate/200.)))<100,"source-only F0 is wrong on a known periodic fixture");
            need(!window.interharmonic[26]&&window.interharmonic[32],"harmonic400/interharmonic500 mask membership is wrong");
        } else need(std::all_of(window.interharmonic.begin(),window.interharmonic.end(),[](uint8_t x){return !x;}),"fallback window retained a voiced mask");
    }
    // Independently reconstruct the aggregate score and source magnitudes from
    // direct DFTs. Descriptors provide the frozen mask/normalization contract.
    double magnitude=0,noise=0;
    for(const auto& window:frozen) {
        const auto x=magnitudes(source,window.start),y=magnitudes(lowerSseNoise,window.start);
        double a=0,b=0;
        for(int k=0;k<=256;++k) {
            close(window.sourceMagnitude[k],x[k],2e-7,"source descriptor differs from direct Hann DFT");
            const double d=y[k]-x[k],weight=k==0||k==256?1:2;
            a+=weight*d*d;if(window.interharmonic[k]&&d>0)b+=weight*d*d;
        }
        need(window.normalization>0&&std::isfinite(window.normalization),"source normalization lacks a finite positive floor");
        magnitude+=a/window.normalization;noise+=b/window.normalization;
    }
    magnitude/=frozen.size();noise/=frozen.size();
    close(trade.magnitude[0],magnitude,2e-10,"magnitude loss differs from independent DFT oracle");
    close(trade.interharmonic[0],noise,2e-10,"positive squared magnitude excess differs from independent DFT oracle");
    close(trade.score,magnitude+2*noise,2e-10,"noise weight or aggregate normalization is wrong");
    std::printf("PASS metric: %d numerical, frozen-mask, harmonic and SSE-tradeoff contracts.\n",contracts);
}
void fallback() {
    for(int rate:{8000,12000,16000}) {
        const int count=rate/4;Pcm noise(count);uint32_t state=0x123abc;
        for(auto& sample:noise){state=state*1664525u+1013904223u;sample=int16_t((int(state>>16)-32768)/8);}
        auto transient=tone(count,rate,4000,200);std::fill(transient.begin()+rate/25,transient.end(),0);
        const Pcm silence(count,0);const auto quiet=tone(count,rate,10,200);
        const Pcm* sources[]={&noise,&transient,&silence,&quiet};
        for(const Pcm* source:sources) {
            LocalNoiseContext context(*source,rate,QualityTarget::Pcm);
            const auto exact=context.measure(*source),muted=context.measure(Pcm(count,0));
            need(exact.valid&&muted.valid&&std::isfinite(muted.score),"fallback score is invalid or non-finite");
            close(exact.score,0,1e-14,"fallback exact source does not minimize loss");
            need(exact.voicedWindows==0,"quiet, unvoiced or transient source received voiced penalty");
            close(muted.interharmonic[0],0,1e-14,"fallback source gained an interharmonic penalty");
            if(source!=&silence)need(muted.score>exact.score,"fallback rewards deleting legitimate source energy");
            if(source==&transient)need(exact.transientWindows>0,"source transient guard was not exercised");
            if(source==&quiet||source==&silence)need(exact.quietWindows>0,"quiet guard was not exercised");
        }
        const auto source=tone(count,rate,4000,200),candidate=perturbed(source,rate,600,500);
        LocalNoiseContext native(source,rate,QualityTarget::Pcm),both(source,rate,QualityTarget::Pwm);
        const auto first=native.measure(candidate),second=native.measure(manualPwm(candidate)),actual=both.measure(candidate);
        need(sameAnalysis(native.analysis(),both.analysis()),"PWM target changed source-derived masks");
        close(actual.magnitude[0],first.magnitude[0],1e-14,"PWM target changed PCM loss");
        close(actual.magnitude[1],second.magnitude[0],1e-14,"PWM loss does not use the original fixed transfer");
        close(actual.interharmonic[1],second.interharmonic[0],1e-14,"PWM noise path has another source or mask");
        close(actual.score,(first.score+second.score)/2,1e-14,"PWM target does not average its two active paths");
    }
    const Pcm empty,shortSource(19,10);LocalNoiseContext none(empty,8000,QualityTarget::Pcm),shortContext(shortSource,8000,QualityTarget::Pcm);
    need(!none.measure(empty).valid,"empty source produced valid analysis");
    need(!shortContext.measure(Pcm(18,10)).valid,"candidate size mismatch was accepted");
    need(shortContext.measure(shortSource).unsupportedWindows>0,"unsupported tail fallback was not exercised");
    need(!LocalNoiseContext(shortSource,11025,QualityTarget::Pcm).measure(shortSource).valid,"unsupported sampling rate was accepted");
    need(!LocalNoiseContext(shortSource,8000,QualityTarget(7)).measure(shortSource).valid,"invalid target was accepted");
    std::printf("PASS fallback: %d quiet, unvoiced, transient, target and unsupported-input contracts.\n",contracts);
}
Stream fixture(int count,int profile,QualityTarget target=QualityTarget::Pcm) {
    Stream value;value.samples=count;value.profile=profile;value.pre=0;value.bright=0;value.qualityTarget=target;
    const int frames=(count+319)/320;Spectrum bins;
    for(int i=0;i<10;++i)bins[i]=(i+1)*(profile==4?32:64)/11;
    value.spectra.assign(frames,bins);value.parameters.assign(frames*2,Parameters{{24,18,0}});
    value.pulses.assign(frames*16,Pulse{{0,profile==4?-8:0}});value.extras.assign(frames*8,Pulse{{-1,0}});
    return value;
}
void preserved(const Stream& old,const Stream& next) {
    need(old.samples==next.samples&&old.rate==next.rate&&old.profile==next.profile&&old.pre==next.pre&&old.bright==next.bright
        &&old.accuracy==next.accuracy&&old.qualityTarget==next.qualityTarget&&old.continuation==next.continuation&&old.allowExtras==next.allowExtras,
        "non-pulse scalar metadata changed");
    need(old.spectra==next.spectra&&old.parameters==next.parameters&&old.extras==next.extras,"coefficient, pitch, gain, scale or extras changed");
    need(old.previousSpectrum==next.previousSpectrum&&old.previousInput==next.previousInput&&old.previousCoefficients==next.previousCoefficients
        &&old.lookahead==next.lookahead&&old.initial.dd==next.initial.dd&&old.initial.cc==next.initial.cc
        &&std::equal(old.initial.h,old.initial.h+10,next.initial.h)&&std::equal(old.initial.ring,old.initial.ring+256,next.initial.ring),
        "continuation or initial synthesis history changed");
    need(old.pulses.size()==next.pulses.size()&&packV9(old).size()==packV9(next).size(),"complete actual byte count changed");
    for(size_t i=0;i<next.pulses.size();++i) {
        const auto& p=next.pulses[i];need(p[0]>=0&&p[0]<20&&p[1]>=-8&&p[1]<=(old.profile==4?8:7),"illegal pulse symbol");
        if(old.profile==4)need(p[0]%5!=2&&(p[1]==-8||p[1]==8),"illegal P4 fixed-width symbol");
        if(i*20>=size_t(old.samples))need(p==old.pulses[i],"untouched out-of-play tail pulse changed");
    }
    need(verifyStream(next,render(next)),"native integer decoder differs from the experimental stream");
}
void floors(const Stream& baseline,const Stream& next,const Pcm& reference) {
    preserved(baseline,next);if(packV9(baseline)==packV9(next))return;
    const auto before=render(baseline),after=render(next);QualityContext quality(reference,true,baseline.rate,baseline.qualityTarget);
    const auto a=quality.measure(before),b=quality.measure(after);
    need(noRegression(b.quality,a.quality),"active-path waveform/STOI floor regressed");
    need(b.clipped<=a.clipped,"accepted output clips more samples");
    for(int path=0;path<qualityPathCount(baseline.qualityTarget);++path)need(b.noise[path]<=a.noise[path]+1e-12,"old source-frozen noise floor regressed");
    FullBandContext bands(reference,baseline.rate,baseline.qualityTarget);
    need(bands.accepts(bands.measure(after),bands.measure(before)),"old complete full-band floor regressed");
    need(stableLpcStream(next)&&safeSynthesisLevel(next,reference,after)&&safeSynthesisSpectrum(reference,after),"accepted output violates stability, level or power-spectrum guards");
    need(profileQualityAdmission(reference,before,after,baseline.rate,true,false,baseline.qualityTarget),"accepted output fails original complete objective");
}
void bounded(const LocalNoiseReport& r,int count) {
    need(!r.error,"valid completed-stream refinement failed");
    need(r.regions>=0&&r.regions<=4&&r.pairs<=4*r.regions,"region/pair search bounds exceeded");
    need(r.localEvaluations<=uint64_t(4*4*(302+4*302)),"legal-symbol/first-choice evaluation bound exceeded");
    need(r.fullEvaluations<=8&&r.noiseProposals<=4&&r.sseProposals<=4,"complete proposal/backoff bounds exceeded");
    need(r.synthesizedSamples<=r.localEvaluations*808+uint64_t(count)*20,"bounded horizon/prefix work exceeded");
    need(r.pcmSseEvaluations>=r.localEvaluations&&r.activeSseEvaluations>=r.localEvaluations,"local SSE accounting omitted evaluated candidates");
}
void search() {
    int changed=0;
    for(int profile:{4,6})for(int count:{1,20,41,321,1027}) {
        auto baseline=fixture(count,profile),target=baseline;target.pulses[0]=Pulse{{count>18?18:0,profile==4?8:7}};
        if(count>20)target.pulses[1]=Pulse{{9,profile==4?8:7}};
        const auto reference=render(target);const auto original=packV9(baseline);LocalNoiseReport report;
        Stream raw,sseRaw,control;const auto selected=refineLocalNoise(baseline,reference,report,&raw,&sseRaw,&control);
        bounded(report,count);need(packV9(baseline)==original,"caller incumbent was mutated");
        const Stream* outputs[]={&raw,&sseRaw,&control,&selected};
        for(const Stream* value:outputs)preserved(baseline,*value);
        floors(baseline,selected,reference);floors(baseline,control,reference);
        changed+=packV9(sseRaw)!=original;
        if(count==321) {
            LocalNoiseReport repeat;Stream againRaw,againSse,againControl;
            const auto again=refineLocalNoise(baseline,reference,repeat,&againRaw,&againSse,&againControl);
            need(packV9(again)==packV9(selected)&&packV9(againRaw)==packV9(raw)&&packV9(againSse)==packV9(sseRaw)
                &&packV9(againControl)==packV9(control),"identical fixed search is not deterministic");
            need(repeat.localEvaluations==report.localEvaluations&&repeat.noiseEvaluations==report.noiseEvaluations
                &&repeat.synthesizedSamples==report.synthesizedSamples,"deterministic search work counts differ");
        }
    }
    need(changed>0,"bounded search never produced an actual excitation proposal");
    std::printf("PASS search: %d fixed-byte, legal pulse, partial-tail, bounded work and deterministic decode contracts.\n",contracts);
}
void admission() {
    int admittedChanges=0;
    for(QualityTarget target:{QualityTarget::Pcm,QualityTarget::Pwm}) {
        auto baseline=fixture(1027,6,target),attainable=baseline;attainable.pulses[0]=Pulse{{9,7}};attainable.pulses[1]=Pulse{{9,7}};
        const auto reference=render(attainable);LocalNoiseReport report;Stream raw,sseRaw,control;
        const auto selected=refineLocalNoise(baseline,reference,report,&raw,&sseRaw,&control);bounded(report,baseline.samples);
        floors(baseline,selected,reference);floors(baseline,control,reference);
        admittedChanges+=packV9(selected)!=packV9(baseline);admittedChanges+=packV9(control)!=packV9(baseline);
        need(report.admittedNoiseProposals<=report.noiseProposals&&report.admittedSseProposals<=report.sseProposals,"separate pool admission accounting is inconsistent");
        if(target==QualityTarget::Pcm)need(report.pwmSseEvaluations==0,"PCM excitation ranking depends on PWM SSE");
        else need(report.pwmSseEvaluations>0,"PWM active-path SSE control ignored PWM");
    }
    need(admittedChanges>0,"constructed reachable target never exercised an admitted change");
    // Recover a real continuous prefix state, then refine only its remaining
    // chunk. No reset or hand-invented decoder history is substituted.
    auto whole=fixture(1601,6);for(auto& p:whole.parameters)p[2]=6;
    whole.pulses[0]=Pulse{{9,7}};auto co=coefficientTrace(whole);SynthesisState state=whole.initial;
    const auto prefix=advance(whole,co,0,1280,state);
    auto continued=whole;continued.samples=321;continued.continuation=true;continued.initial=state;
    continued.previousSpectrum=whole.spectra[3];continued.spectra.assign(whole.spectra.begin()+4,whole.spectra.end());
    continued.parameters.assign(whole.parameters.begin()+8,whole.parameters.end());continued.pulses.assign(whole.pulses.begin()+64,whole.pulses.end());
    continued.extras.assign(whole.extras.begin()+32,whole.extras.end());
    std::copy(prefix.end()-172,prefix.end(),continued.previousInput.begin());
    std::copy(co.begin()+56,co.begin()+64,continued.previousCoefficients.begin());
    auto expected=continued;expected.pulses[0]=Pulse{{9,7}};const auto reference=render(expected);
    LocalNoiseReport report;Stream raw,sseRaw,control;const auto selected=refineLocalNoise(continued,reference,report,&raw,&sseRaw,&control);
    bounded(report,321);floors(continued,selected,reference);floors(continued,control,reference);preserved(continued,raw);preserved(continued,sseRaw);
    // Existing verifyStream deliberately checks isolated reset arithmetic for
    // a continuation chunk. Assemble the real untouched prefix and test every
    // native sample against its carried-state suffix, including the final EOF.
    const Stream* outputs[]={&selected,&control,&raw,&sseRaw};
    for(const Stream* output:outputs) {
        auto assembled=whole;std::copy(output->pulses.begin(),output->pulses.end(),assembled.pulses.begin()+64);
        const auto bytes=packV9(assembled);const auto suffix=render(*output);Lpx4HybridCore decoder;
        need(decoder.beginWideV9(bytes.data(),bytes.size()),"assembled continuation failed native begin");
        for(int at=0;at<whole.samples;++at) {
            int16_t actual;const int expected=at<1280?prefix[at]:suffix[at-1280];
            need(decoder.nextS16(actual)&&actual==expected,"assembled native output differs from carried-state synthesis");
        }
        int16_t tail;need(!decoder.nextS16(tail)&&!decoder.error()&&decoder.finished(),"assembled continuation EOF failed");
    }
    auto invalid=continued;invalid.qualityTarget=QualityTarget(7);LocalNoiseReport rejected;
    refineLocalNoise(invalid,reference,rejected);need(rejected.error<0,"invalid target was accepted by refinement");
    // A played P4 zero amplitude is not faithfully represented by its sign-only
    // pulse syntax. The model may be parsed structurally, but native roundtrip
    // rejection must happen before any local search can hide the discrepancy.
    auto malformed=fixture(41,4);malformed.pulses[0]=Pulse{{0,0}};
    const auto malformedPcm=render(malformed);LocalNoiseReport nativeRejected;
    refineLocalNoise(malformed,malformedPcm,nativeRejected);
    need(nativeRejected.error==-3&&nativeRejected.localEvaluations==0,"played P4 zero-amplitude model bypassed entry native verification");
    auto unstable=fixture(41,6);
    for(auto& spectrum:unstable.spectra)for(int i=0;i<10;++i)spectrum[i]=i;
    need(!stableLpcStream(unstable),"clustered legal LSF fixture did not exercise quantized instability");
    LocalNoiseReport stabilityRejected;refineLocalNoise(unstable,render(unstable),stabilityRejected);
    need(stabilityRejected.error==-2&&stabilityRejected.localEvaluations==0,"unstable completed predictor entered local search");
    std::printf("PASS admission: %d independent-pool quality/stability/power/target and true-continuation contracts.\n",contracts);
}
}
int main(int argc,char** argv) {
    need(argc==2,"select metric, fallback, search or admission");const std::string mode=argv[1];
    if(mode=="metric")metric();else if(mode=="fallback")fallback();else if(mode=="search")search();else if(mode=="admission")admission();else return 2;
}
