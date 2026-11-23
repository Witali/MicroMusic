#include "LpxAccuracy.h"
#include "LpxProfileQuality.h"
#include <algorithm>
namespace lpx{
AccuracyPolicy accuracyPolicy(int level){
    AccuracyPolicy p;if(level!=3&&level!=4&&level!=6&&level!=8)return p;
    p.level=level;p.wireProfile=level<=4?4:6;p.detailBitsPerFrame=40*level;p.corrections=level==8;return p;
}
int accuracyPacketBound(int samples,int level){
    auto p=accuracyPolicy(level);if(!p.level||samples<1)return 0;
    // A worst-case bound of the legal quantized syntax, not a target bitrate.
    const int spectral=2+10*(8+(p.wireProfile==4?5:6)+1);
    return 22+int((int64_t((samples+319)/320)*(spectral+(p.wireProfile==4?110:166)+(p.corrections?88:0))+7)/8);
}
int accuracyBudget(int samples,int level,int originalBytes){
    auto p=accuracyPolicy(level);if(!p.level||samples<1)return 0;
    return std::max(originalBytes,(samples>64000?17:13)+int((int64_t((samples+319)/320)*p.detailBitsPerFrame+7)/8));
}
static Stream correctionLayer(const Stream& input,const Pcm& reference,int budget){
    Stream work=input;auto co=coefficientTrace(work);auto state=work.initial;
    struct Proposal{int index,bits;uint64_t gain;Pulse value;};std::vector<Proposal> proposals;
    for(int at=0;at<work.samples;at+=40){
        int stop=std::min(work.samples,at+160),index=at/40,valid=std::min(40,work.samples-at);
        auto initial=state;auto baseline=advance(work,co,at,stop,initial);uint64_t best=sse(reference,baseline,at);Pulse chosen=work.extras[index];
        int peak=0;for(int i=1;i<valid;++i)if(std::abs(int(reference[at+i])-int(baseline[i]))>std::abs(int(reference[at+peak])-int(baseline[peak])))peak=i;
        for(int pos=std::max(0,peak-1);pos<=std::min(valid-1,peak+1);++pos)for(int amp=-8;amp<=7;++amp)if(amp){
            work.extras[index]=Pulse{{pos,amp}};auto trialState=state;auto pcm=advance(work,co,at,stop,trialState);uint64_t loss=sse(reference,pcm,at);
            if(loss<best){best=loss;chosen=work.extras[index];}
        }
        if(chosen!=input.extras[index])proposals.push_back({index,input.extras[index][0]<0?10:0,sse(reference,baseline,at)-best,chosen});
        work.extras[index]=input.extras[index];advance(work,co,at,std::min(work.samples,at+40),state);
    }
    // Rank reconstructed benefit per extra symbol bit, never magnitude.
    std::stable_sort(proposals.begin(),proposals.end(),[](const Proposal&a,const Proposal&b){
        if(!a.bits||!b.bits)return a.bits==b.bits?a.gain>b.gain:a.bits<b.bits;
        return a.gain*uint64_t(b.bits)>b.gain*uint64_t(a.bits);
    });
    // Header, spectrum/repeats and presence flags are already in these bytes.
    // Padding is conservatively counted; a newly present extra costs ten bits.
    int64_t bits=int64_t(packV9(work).size())*8;
    for(const auto& proposal:proposals)if((bits+proposal.bits+7)/8<=budget){work.extras[proposal.index]=proposal.value;bits+=proposal.bits;}
    if(int(packV9(work).size())>budget)return input;
    return work;
}
Stream encodeAccuracy(const Pcm& reference,int level,int rate,AdaptiveReport& report,int calls,const Stream* prefix){
    report=AdaptiveReport{};const auto policy=accuracyPolicy(level);
    if(!policy.level||reference.empty()||(rate!=8000&&rate!=12000&&rate!=16000)||calls<0||calls>4){report.error=-1;return Stream{};}
    Stream context=prefix?*prefix:Stream{};context.accuracy=level;
    // One policy drives the common search. Windowed P4/P6 preserve their
    // existing no-extras syntax; P8 carries explicit correction parameters.
    context.allowExtras=policy.corrections||(!prefix&&(level==4||level==6));
    const int pre=context.continuation?context.pre:13926;
    Stream control=fitSeed(reference,policy.wireProfile,rate,pre,false,.97,&context);
    if(control.samples!=int(reference.size())){report.error=-7;return Stream{};}
    control=canonicalAccuracy(control);
    const auto originalControl=control;
    const int budget=accuracyBudget(reference.size(),level,packV9(control).size());
    if(policy.corrections){auto corrected=correctionLayer(control,reference,budget);
        if(profileQualityAdmission(reference,render(control),render(corrected),rate,true,true))control=std::move(corrected);}
    if(!calls)return control;
    // Internal controller accounting is v5; independently enforce final V9
    // bytes below, including its header, flags, repeats and padding.
    Stream candidate=adaptiveEncode(reference,policy.wireProfile,rate,report,false,budget+9,calls,true,true,0,false,&context);
    if(report.error)return Stream{};
    candidate=canonicalAccuracy(candidate);
    // Retain the complete original admissible quantized control. All levels
    // share the same actual-rate, whole-output metric and octave guard.
    ProfileQualityReport selection;
    candidate=selectQualityProposals(originalControl,reference,{&control,&candidate},selection,true,budget);
    if(selection.error){report.error=selection.error;return Stream{};}
    if(!verifyStream(candidate,render(candidate))){report.error=-3;return Stream{};}
    return candidate;
}
}
