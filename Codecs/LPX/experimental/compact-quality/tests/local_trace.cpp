// Independent regression for the private proposal-only LPC coefficient crop.
// Include its implementation only in this TU; the runner omits its normal TU.
#ifndef LPX_LPC_REFINE_SOURCE
#define LPX_LPC_REFINE_SOURCE "LpxLpcRefine.cpp"
#endif
#include LPX_LPC_REFINE_SOURCE
#include "LpxAdaptiveController.h"
#include "Lpx4HybridCore.h"
#include <cstdio>
#include <cstdlib>
#include <string>

namespace {
using namespace lpx;
void need(bool value,const char* message) {
    if(!value) { std::fprintf(stderr,"FAIL: %s\n",message);std::exit(1); }
}
Stream fixture(int n,int level,int rate) {
    Stream s;s.samples=n;s.rate=rate;s.profile=level<=4?4:6;s.accuracy=level;
    s.pre=8192;s.bright=4096;
    const int frames=(n+319)/320;
    Spectrum a;
    for(int j=0;j<10;++j)a[j]=s.profile==4?3*j+(j>=5?4:0):3+5*j;
    if(s.profile==6)a[4]=21;
    s.spectra.assign(frames,a);
    for(int f=0;f<frames;++f)if(f%5==2||f%5==3)s.spectra[f][4]+=4;
    s.parameters.resize(frames*2);
    for(int i=0;i<frames*2;++i)s.parameters[i]={{12+i%3,i%2?37:145,i%3?6:0}};
    s.pulses.resize(frames*16);
    for(int i=0;i<frames*16;++i) {
        int position=(i*7)%20;if(s.profile==4&&position%5==2)++position;
        s.pulses[i]={{position,i%2?-8:(s.profile==4?8:7)}};
    }
    s.extras.assign(frames*8,Pulse{{-1,0}});
    if(n>80)s.extras[1]={{9,2}};
    return canonicalAccuracy(s);
}
Pcm native(const Stream& s) {
    need(!s.continuation,"native oracle requires complete reset stream");
    const auto bytes=packV9(s);need(!bytes.empty(),"native oracle pack failed");
    Lpx4HybridCore decoder;need(decoder.beginWideV9(bytes.data(),bytes.size()),"native oracle begin failed");
    Pcm result(s.samples);
    for(int at=0;at<s.samples;++at)if(!decoder.nextS16(result[at])) {
        std::fprintf(stderr,"fixture level%d/rate%d/n%d at%d native error%d\n",s.accuracy,s.rate,s.samples,at,decoder.error());
        need(false,"native oracle short PCM");
    }
    int16_t tail;need(!decoder.nextS16(tail)&&!decoder.error()&&decoder.finished(),"native PCM EOF failed");
    need(decoder.beginWideV9(bytes.data(),bytes.size()),"native PWM restart failed");
    for(int sample:result) {
        uint8_t actual;need(decoder.next(actual),"native PWM short output");
        const int q14=(sample+1)>>1;
        const int duty=std::max(0,std::min(255,128+((q14*130+8192)>>14)));
        need(actual==duty,"native PCM/PWM transfer differs");
    }
    uint8_t last;need(!decoder.next(last)&&!decoder.error()&&decoder.finished(),"native PWM EOF failed");
    const auto model=render(s);
    if(result!=model) {
        int at=0;while(at<s.samples&&result[at]==model[at])++at;
        std::fprintf(stderr,"fixture level%d/rate%d/n%d at%d native%d/model%d\n",s.accuracy,s.rate,s.samples,at,result[at],model[at]);
        need(false,"complete host render differs from independent native decoder");
    }
    return result;
}
bool stateEqual(const SynthesisState& a,const SynthesisState& b) {
    return a.dd==b.dd&&a.cc==b.cc&&std::equal(a.h,a.h+10,b.h)&&std::equal(a.ring,a.ring+256,b.ring);
}
struct Checks { int cases=0,coefficientMismatches=0,audioMismatches=0,noOps=0,propagated=0; };
void compare(const Stream& trial,const std::vector<Coefficients>& baseline,int start,int end,
             const Pcm& actual,Checks& checks) {
    auto cropped=baseline;
    localCoefficients(trial,start,end,cropped);
    const auto expected=coefficientTrace(trial);
    bool coefficients=true;
    for(int at=start/20;at<(end+19)/20;++at)coefficients&=cropped[at]==expected[at];
    checks.coefficientMismatches+=!coefficients;
    auto prefix=trial.initial;
    advance(trial,expected,0,start,prefix);
    const auto pcm=advance(trial,cropped,start,end,prefix);
    checks.audioMismatches+=!std::equal(pcm.begin(),pcm.end(),actual.begin()+start);
    ++checks.cases;
}
int traces(bool p3) {
    Checks checks;
    const std::vector<int> levels=p3?std::vector<int>{3}:std::vector<int>{4,6,8};
    for(int level:levels)for(int rate:{8000,12000,16000})
      for(int n:{1,19,20,21,39,40,41,159,160,161,319,320,321,641,1601}) {
        const auto base=fixture(n,level,rate);const auto baseline=coefficientTrace(base);
        const auto baseBytes=packV9(base);
        for(int frame=0;frame<int(base.spectra.size());++frame)for(int delta:{-1,1}) {
            auto trial=base;trial.spectra[frame][4]+=delta;
            const auto actual=native(trial);
            checks.noOps+=packV9(trial)==baseBytes;
            const auto canonical=canonicalAccuracy(trial);
            for(int f=0;f<int(base.spectra.size());++f)
                if(f!=frame&&canonical.spectra[f]!=base.spectra[f])++checks.propagated;
            for(int start:{0,320,640,1280})if(start<n)
                compare(trial,baseline,start,std::min(n,start+1280),actual,checks);
        }
    }
    if(p3)need(checks.noOps>0&&checks.propagated>0,"P3 test did not cover canonical no-op and dead-zone propagation");
    std::printf("%s %s: %d crops; coefficient mismatches %d, native-audio mismatches %d; canonical no-ops %d, propagated frames %d\n",
        checks.coefficientMismatches||checks.audioMismatches?"REGRESSION":"PASS",p3?"P3":"P4/P6/P8",checks.cases,
        checks.coefficientMismatches,checks.audioMismatches,checks.noOps,checks.propagated);
    return checks.coefficientMismatches||checks.audioMismatches?30:0;
}
Stream suffix(const Stream& whole,int offset,const Pcm& source) {
    Stream chunk=whole;chunk.samples=whole.samples-offset;chunk.continuation=true;
    const auto co=coefficientTrace(whole);auto state=whole.initial;
    advance(whole,co,0,offset,state);chunk.initial=state;
    chunk.previousSpectrum=whole.spectra[offset/320-1];
    chunk.spectra.assign(whole.spectra.begin()+offset/320,whole.spectra.end());
    chunk.parameters.assign(whole.parameters.begin()+offset/160,whole.parameters.end());
    chunk.pulses.assign(whole.pulses.begin()+offset/20,whole.pulses.end());
    chunk.extras.assign(whole.extras.begin()+offset/40,whole.extras.end());
    std::copy(source.begin()+offset-172,source.begin()+offset,chunk.previousInput.begin());
    std::copy(co.begin()+offset/20-8,co.begin()+offset/20,chunk.previousCoefficients.begin());
    return chunk;
}
int continuation() {
    Checks checks;
    for(int level:{3,4,6,8})for(int rate:{8000,12000,16000})for(int tail:{1,321,1281}) {
        const int offset=1280;auto whole=fixture(offset+tail,level,rate);const auto before=native(whole);
        auto chunk=suffix(whole,offset,before);const auto baseline=coefficientTrace(chunk);
        for(int frame=0;frame<int(chunk.spectra.size());++frame)for(int delta:{-1,1}) {
            auto trial=chunk;trial.spectra[frame][4]+=delta;
            auto assembled=whole;
            std::copy(trial.spectra.begin(),trial.spectra.end(),assembled.spectra.begin()+offset/320);
            const auto full=native(assembled);Pcm actual(full.begin()+offset,full.end());
            need(render(trial)==actual,"carried-state chunk differs from real assembled native suffix");
            for(int start:{0,320,640})if(start<tail)
                compare(trial,baseline,start,std::min(tail,start+1280),actual,checks);
        }
    }
    std::printf("%s continuation: %d real-prefix crops; coefficient mismatches %d, native-audio mismatches %d\n",
        checks.coefficientMismatches||checks.audioMismatches?"REGRESSION":"PASS",checks.cases,checks.coefficientMismatches,checks.audioMismatches);
    return checks.coefficientMismatches||checks.audioMismatches?30:0;
}
void unchanged(const Stream& base,const Stream& result) {
    need(base.samples==result.samples&&base.rate==result.rate&&base.profile==result.profile&&base.accuracy==result.accuracy
        &&base.qualityTarget==result.qualityTarget&&base.pre==result.pre&&base.bright==result.bright
        &&base.parameters==result.parameters&&base.extras==result.extras&&base.continuation==result.continuation
        &&base.allowExtras==result.allowExtras&&base.previousSpectrum==result.previousSpectrum
        &&base.previousInput==result.previousInput&&base.previousCoefficients==result.previousCoefficients
        &&base.lookahead==result.lookahead&&stateEqual(base.initial,result.initial),"LPC proposal modified unrelated metadata/history");
    need(base.spectra.size()==result.spectra.size()&&base.pulses.size()==result.pulses.size(),"LPC proposal changed vector geometry");
    for(int i=0;i<int(base.pulses.size());++i)if(base.pulses[i]!=result.pulses[i]) {
        const auto p=result.pulses[i];need(i*20<base.samples&&p[0]>=0&&p[0]<20,"LPC proposal changed unplayed/invalid pulse");
        need(p[1]>=-8&&p[1]<=(base.profile==4?8:7),"LPC proposal amplitude invalid");
        if(base.profile==4)need(p[0]%5!=2&&(p[1]==-8||p[1]==8),"P4 pulse is not representable by its5bit alphabet");
    }
}
int proposals() {
    int cases=0,proposals=0;
    for(int level:{3,4,6,8})for(int rate:{8000,12000,16000}) {
        auto input=fixture(321,level,rate),target=input;target.spectra[0][4]+=1;
        const auto reference=native(target);const auto original=packV9(input);const int cap=original.size();
        const auto result=proposeLpcRuns(input,reference,cap,true);
        const auto repeated=proposeLpcRuns(input,reference,cap,true);
        need(packV9(input)==original,"proposal search mutated original input");
        need(result.proposals.size()==repeated.proposals.size(),"proposal count nondeterministic");
        need(result.spectralEvaluations==repeated.spectralEvaluations&&result.pulseEvaluations==repeated.pulseEvaluations
            &&result.synthesizedSamples==repeated.synthesizedSamples,"proposal work nondeterministic");
        need(result.runs<=4&&result.spectralEvaluations<=80&&result.proposals.size()<=8,"proposal bound exceeded");
        for(size_t i=0;i<result.proposals.size();++i) {
            const auto& proposal=result.proposals[i];unchanged(input,proposal);const auto bytes=packV9(proposal);
            need(bytes!=original&&int(bytes.size())<=cap,"no-op or over-budget proposal retained");
            need(bytes==packV9(repeated.proposals[i]),"serialized proposal nondeterministic");
            native(proposal);++proposals;
        }
        const auto noFit=proposeLpcRuns(input,reference,cap-1,true);
        need(noFit.proposals.empty()&&!noFit.spectralEvaluations&&!noFit.pulseEvaluations,"over-budget baseline entered search");
        auto pure=input;pure.qualityTarget=QualityTarget::Pcm;
        const auto perfect=proposeLpcRuns(pure,native(pure),cap,true);
        need(perfect.proposals.empty(),"exact decoded target produced a spurious improving proposal");
        ++cases;
    }
    std::printf("PASS proposals: %d profile/rate cases; %d legal non-no-op native proposals; deterministic, capped, metadata preserved\n",cases,proposals);
    return 0;
}
}
int main(int argc,char** argv) {
    need(argc==2,"select trace, controls, continuation or proposals");const std::string mode=argv[1];
    if(mode=="trace")return traces(true);if(mode=="controls")return traces(false);
    if(mode=="continuation")return continuation();if(mode=="proposals")return proposals();return 2;
}
