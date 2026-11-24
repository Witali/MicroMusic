#include "LpxAccuracy.h"
#include "LpxEncodingPolicy.h"
#include "LpxCandidateEvaluation.h"
#include "LpxProfileQuality.h"
#include <algorithm>
namespace lpx{
AccuracyPolicy accuracyPolicy(int level){
    AccuracyPolicy p;const auto selected=encodingPolicy(level,true);if(!selected.valid())return p;
    p.level=selected.accuracyLevel;p.wireProfile=selected.wireProfile;
    p.detailBitsPerFrame=40*level;p.corrections=selected.corrections;return p;
}
int accuracyPacketBound(int samples,int level){
    auto p=accuracyPolicy(level);if(!p.level||samples<1)return 0;
    // A worst-case bound of the legal quantized syntax, not a target bitrate.
    const int spectral=2+10*(8+(p.wireProfile==4?5:6)+1);
    return 22+int((int64_t((samples+319)/320)*(spectral+(p.wireProfile==4?110:166)+(p.corrections?88:0))+7)/8);
}
int accuracyBudget(int samples,int level,int originalBytes){
    auto p=accuracyPolicy(level);if(!p.level||samples<1)return 0;
    return std::max(originalBytes,v9HeaderBytes(samples)+int((int64_t((samples+319)/320)*p.detailBitsPerFrame+7)/8));
}
Stream refineAccuracyCorrections(const Stream& input,const Pcm& reference,int budget){
    Stream work=input;
    const bool hasDetails=std::any_of(work.extras.begin(),work.extras.end(),[](const Pulse&p){return p[1]!=0;});
    if(!hasDetails) {
        // Low budgets use this same operator, but cannot pay to activate a
        // detail layer. Avoid expensive proposals that can never fit.
        if(work.extras.empty())return input;
        const auto old=work.extras[0];work.extras[0]=Pulse{{0,1}};
        const bool fits=int(packV9(work).size())<=budget;work.extras[0]=old;
        if(!fits)return input;
    }
    auto co=coefficientTrace(work);auto state=work.initial;
    struct Proposal{int index,bits;uint64_t gain;Pulse value;};std::vector<Proposal> proposals;
    for(int at=0;at<work.samples;at+=40){
        int stop=std::min(work.samples,at+160),index=at/40,valid=std::min(40,work.samples-at);
        auto initial=state;auto baseline=advance(work,co,at,stop,initial);uint64_t best=sse(reference,baseline,at);Pulse chosen=work.extras[index];
        int peak=0;for(int i=1;i<valid;++i)if(std::abs(int(reference[at+i])-int(baseline[i]))>std::abs(int(reference[at+peak])-int(baseline[peak])))peak=i;
        // Integer SSE has an exact zero lower bound. Preserve the incumbent
        // and its usual state advance without evaluating impossible gains.
        if(best)for(int pos=std::max(0,peak-1);pos<=std::min(valid-1,peak+1);++pos)for(int amp=-8;amp<=7;++amp)if(amp){
            work.extras[index]=Pulse{{pos,amp}};auto trialState=state;auto pcm=advance(work,co,at,stop,trialState);uint64_t loss=sse(reference,pcm,at);
            if(loss<best){best=loss;chosen=work.extras[index];}
        }
        if(chosen!=input.extras[index])proposals.push_back({index,input.extras[index][1]==0?10:0,sse(reference,baseline,at)-best,chosen});
        work.extras[index]=input.extras[index];advance(work,co,at,std::min(work.samples,at+40),state);
    }
    // Rank reconstructed benefit per extra symbol bit, never magnitude.
    std::stable_sort(proposals.begin(),proposals.end(),[](const Proposal&a,const Proposal&b){
        if(!a.bits||!b.bits)return a.bits==b.bits?a.gain>b.gain:a.bits<b.bits;
        return a.gain*uint64_t(b.bits)>b.gain*uint64_t(a.bits);
    });
    // The first active extra enables a presence bit for every actual group.
    // Exact-pack that first activation; subsequent new symbols cost ten bits.
    // Existing padding is conservatively reserved, never borrowed twice.
    int64_t bits=int64_t(packV9(work).size())*8;
    bool enhanced=std::any_of(work.extras.begin(),work.extras.end(),[](const Pulse&p){return p[1]!=0;});
    for(const auto& proposal:proposals){
        if(!enhanced){
            const auto previous=work.extras[proposal.index];work.extras[proposal.index]=proposal.value;
            const int bytes=packV9(work).size();
            if(bytes>budget){work.extras[proposal.index]=previous;break;}
            bits=int64_t(bytes)*8;enhanced=true;
        }else if((bits+proposal.bits+7)/8<=budget){work.extras[proposal.index]=proposal.value;bits+=proposal.bits;}
    }
    if(int(packV9(work).size())>budget)return input;
    return work;
}
Stream encodeAccuracy(const Pcm& reference,int level,int rate,AdaptiveReport& report,int calls,const Stream* prefix){
    report=AdaptiveReport{};const auto policy=accuracyPolicy(level);
    if(!policy.level||reference.empty()||(rate!=8000&&rate!=12000&&rate!=16000)||calls<0||calls>4){report.error=-1;return Stream{};}
    Stream context=prefix?*prefix:Stream{};context.accuracy=level;
    // One base model and one detail operator for every level and transport.
    // The exact bit budget decides how many ranked residual symbols survive.
    context.allowExtras=true;
    const int pre=context.continuation?context.pre:13926;
    const Stream seed=fitSeed(reference,policy.wireProfile,rate,pre,false,.97,&context);
    Stream control=seed;
    if(control.samples!=int(reference.size())){report.error=-7;return Stream{};}
    control=canonicalAccuracy(control);
    const auto originalControl=control;
    const int budget=accuracyBudget(reference.size(),level,packV9(control).size());
    auto corrected=refineAccuracyCorrections(control,reference,budget);
    if(packV9(corrected)!=packV9(control)) {
        const auto originalPcm=render(control),detailPcm=render(corrected);
        if(safeSynthesisLevel(corrected,reference,detailPcm)&&safeSynthesisSpectrum(reference,detailPcm)
            &&profileQualityAdmission(reference,originalPcm,detailPcm,rate,true,true))control=std::move(corrected);
    }
    if(!calls)return control;
    // Internal controller accounting is v5; independently enforce final V9
    // bytes below, including its header, flags, repeats and padding.
    CandidateEvaluation evaluation(reference,rate,true);
    Stream candidate=adaptiveEncode(reference,policy.wireProfile,rate,report,false,std::max(budget+9,compactBytes(seed)),calls,true,true,0,false,&context,&seed,&evaluation);
    if(report.error==-6) {
        // The complete common control already fits this profile. Internal
        // legacy-v5 proposal accounting cannot invalidate that legal floor.
        report.error=0;report.cap=budget;report.selected=-1;return control;
    }
    if(report.error)return Stream{};
    candidate=canonicalAccuracy(candidate);
    // Retain the complete original admissible quantized control. All levels
    // share the same actual-rate, whole-output metric and octave guard.
    ProfileQualityReport selection;
    candidate=selectQualityProposals(originalControl,reference,{&control,&candidate},selection,true,budget,&evaluation);
    if(selection.error){report.error=selection.error;return Stream{};}
    if(!verifyStream(candidate,render(candidate))){report.error=-3;return Stream{};}
    return candidate;
}
}
