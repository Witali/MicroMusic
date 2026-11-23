// Shared controller corresponding to adaptive_speech_voice.encode/refine_candidates.
// Python is an independent test oracle, never a runtime dependency.
#include "LpxAdaptiveController.h"
#include "LpxRefinement.h"
#include "Lpx4HybridCore.h"
#include <algorithm>
#include <cmath>
#include <tuple>

namespace lpx {
bool verifyStream(const Stream& stream,const Pcm& expected) {
    auto bytes=packV9(stream);Lpx4HybridCore decoder;
    if(!decoder.beginWideV9(bytes.data(),bytes.size()))return false;
    for(int value:expected) { int16_t actual;if(!decoder.nextS16(actual) || actual!=value)return false; }
    int16_t tail;return !decoder.nextS16(tail) && !decoder.error() && decoder.finished();
}
static bool sameStream(const Stream& a,const Stream& b) {
    return a.pre==b.pre && a.bright==b.bright && a.spectra==b.spectra && a.parameters==b.parameters && a.pulses==b.pulses && a.extras==b.extras;
}
Stream adaptiveEncode(const Pcm& input,int profile,int rate,AdaptiveReport& report,
                      bool autoQuiet,int cap,int calls,bool speech,bool expandedSearch,int sizeAllowancePercent) {
    report=AdaptiveReport{};
    if(sizeAllowancePercent<0 || sizeAllowancePercent>100) { report.error=-1;return Stream{}; }
    Pcm reference=input;
    if(autoQuiet) {
        double mean=0,energy=0,peak=0;
        for(int x:reference) { mean+=x;peak=std::max(peak,std::abs(double(x))); } mean/=reference.size();
        for(int x:reference) { double d=x-mean;energy+=d*d; }double rms=std::sqrt(energy/reference.size());
        if(rms && rms<256)while(std::ldexp(rms,report.gainExponent)<1024 && std::ldexp(peak,report.gainExponent+1)<=29490)++report.gainExponent;
        for(auto& x:reference)x=int(x)*(1<<report.gainExponent);
    }
    QualityContext context(reference,speech);
    std::vector<Stream> seeds;seeds.push_back(fitSeed(reference,profile,rate,13926,false));
    if(!seeds.back().samples) { report.error=-7;return Stream{}; }
    if(!cap)cap=int(int64_t(compactBytes(seeds[0]))*(100+sizeAllowancePercent)/100);report.cap=cap;
    auto originalPcm=render(seeds[0]);auto original=context.measure(originalPcm);
    Stream anchor=seeds[0];double selectedScore=original.voice[0];
    for(int pre:{0,8192,13926}) {
        seeds.push_back(fitSeed(reference,profile,rate,pre,true));
        if(!seeds.back().samples) { report.error=-7;return Stream{}; }
        auto pcm=render(seeds.back());auto m=context.measure(pcm);
        if(compactBytes(seeds.back())<=cap && noRegression(m.quality,original.quality)
            && voiceGate(m.diagnostic[0],original.diagnostic[0]) && voiceGate(m.diagnostic[1],original.diagnostic[1])
            && m.voice[0]<selectedScore) { anchor=seeds.back();selectedScore=m.voice[0]; }
    }
    struct Candidate { Stream stream;Measurement measured;int bytes,origin;bool attempted[3]={}; };
    std::vector<Candidate> pool;
    auto add=[&](const Stream& stream,int origin)->int {
        for(int i=0;i<int(pool.size());++i)if(sameStream(stream,pool[i].stream))return i;
        auto pcm=render(stream);
        if(!verifyStream(stream,pcm)) { report.error=-3;return -1; }
        Candidate candidate;candidate.stream=stream;candidate.measured=context.measure(pcm);candidate.bytes=compactBytes(stream);candidate.origin=origin;
        pool.push_back(std::move(candidate));return pool.size()-1;
    };
    if(add(anchor,-1)<0)return Stream{};report.baseline=pool[0].measured;
    auto allowed=[&](int i)->bool {
        const auto& m=pool[i].measured;const auto& base=pool[0].measured;
        return pool[i].bytes<=cap && m.score<=base.score+1e-12 && noRegression(m.quality,base.quality)
            && m.clipped<=base.clipped && m.diagnostic[0].within>=base.diagnostic[0].within && m.diagnostic[1].within>=base.diagnostic[1].within;
    };
    for(const auto& seed:seeds)if(add(seed,-2)<0)return Stream{};
    auto ranked=[&](bool preferAllowed)->std::vector<int> {
        std::vector<int> order;for(int i=0;i<int(pool.size());++i)if(pool[i].bytes<=cap)order.push_back(i);
        std::sort(order.begin(),order.end(),[&](int a,int b) {
            if(preferAllowed && allowed(a)!=allowed(b))return allowed(a);
            return std::tie(pool[a].measured.score,pool[a].bytes,a)<std::tie(pool[b].measured.score,pool[b].bytes,b);
        });return order;
    };
    for(int stage=0;stage<calls;++stage) {
        int parent=-1,operation=-1;
        for(int i:ranked(true)) {
            for(int op=0;op<3;++op) {
                auto& c=pool[i];if(c.attempted[op])continue;c.attempted[op]=true;
                if(c.origin==op)continue;
                if(op==0) {
                    bool extras=false;for(const auto& e:c.stream.extras)extras|=e[1]!=0;
                    if(extras || !extraCapacity(c.stream,cap,(reference.size()+39)/40))continue;
                }
                parent=i;operation=op;break;
            }
            if(parent>=0)break;
        }
        if(parent<0)break;
        // Copy before additions: vector growth must not invalidate the parent.
        Stream source=pool[parent].stream;
        RefinementResult result=operation==0?enhanceExtras(source,context,cap):operation==1?refineHeader(source,context):refineLpc(source,context,cap);
        add(result.selected,operation);
        if(operation!=0)add(result.raw,operation);
        if(operation==1)for(const auto& alternative:result.alternatives)add(alternative,operation);
        if(report.error)return Stream{};
        report.stageOperator[stage]=operation;report.localEvaluations[stage]=result.localEvaluations;report.fullEvaluations[stage]=result.fullEvaluations;
        ++report.stages;
    }
    if(expandedSearch) {
        int parent=-1;for(int i:ranked(false))if(allowed(i)) { parent=i;break; }
        if(parent>=0) {
            auto extension=refinePitchGain(pool[parent].stream,context,cap);
            add(extension.selected,3);add(extension.raw,3);
            for(const auto& alternative:extension.alternatives)add(alternative,3);
            report.expandedLocalEvaluations=extension.localEvaluations;
            report.expandedFullEvaluations=extension.fullEvaluations;
            report.expandedAccepted=extension.accepted;
            if(report.error)return Stream{};
        }
    }
    report.candidates=pool.size();
    for(int i:ranked(false))if(allowed(i)) { report.selected=i;report.measurement=pool[i].measured;return pool[i].stream; }
    report.error=-6;return Stream{};
}
}
