#include "LpxAccuracy.h"
#include "LpxEncodingPolicy.h"
#include "LpxCandidateEvaluation.h"
#include "LpxProfileQuality.h"
#include "LpxBitrateProfiles.h"
#include <algorithm>
namespace lpx{
namespace {
bool resetCompactState(const Stream& s) {
    if(s.continuation || !s.lookahead.empty() || s.initial.dd || s.initial.cc)return false;
    for(int value:s.initial.h)if(value)return false;
    for(int value:s.initial.ring)if(value)return false;
    return true;
}
bool validCompactModel(const Stream& s) {
    if(!validQualityTarget(s.qualityTarget) || (s.accuracy!=3 && s.accuracy!=4)
        || s.samples<1 || s.samples>64000 || s.rate!=8000 || s.profile!=4
        || s.pre<0 || s.pre>16384 || s.bright<0 || s.bright>11469
        || !resetCompactState(s))return false;
    const int frames=(s.samples+319)/320;
    if(int(s.spectra.size())!=frames || int(s.parameters.size())<frames*2
        || int(s.pulses.size())<frames*16 || int(s.extras.size())<frames*8)return false;
    for(const auto& vector:s.spectra)for(int k=0;k<10;++k)
        if(vector[k]<0 || vector[k]>31 || (k && vector[k]<=vector[k-1]))return false;
    for(int i=0;i<(s.samples+159)/160;++i) {
        const auto& p=s.parameters[i];
        if(p[0]<0 || p[0]>31 || p[1]<18 || p[1]>145
            || p[2]<0 || p[2]>14 || (p[2]&1))return false;
    }
    // A terminal partial packet still transmits both ordinary P4 pulses.
    for(int i=0;i<2*((s.samples+39)/40);++i) {
        const auto& p=s.pulses[i];
        if(p[0]<0 || p[0]>=20 || (p[0]+3)%5==0 || (p[1]!=-8 && p[1]!=8))return false;
    }
    for(int i=0;i<(s.samples+39)/40;++i) {
        const auto& p=s.extras[i];
        if(p[1]<-8 || p[1]>7 || (p[1] && (p[0]<0 || p[0]>=40)))return false;
    }
    return true;
}
void compactFailure(CompactEnsembleReport& report,int status,int error=-1) {
    report.status=status;report.error=error;
}
}
bool compactEnsembleEnabled() {
    return LPX_ENCODER_COMPACT_ENSEMBLE && LPX_ENCODER_QUALITY_SEARCH && LPX_ENCODER_JOINT_REFINEMENT;
}
bool compactEnsembleEligible(const Stream& completed,int calls,const Stream* prefix) {
    return !prefix && calls==4 && validQualityTarget(completed.qualityTarget)
        && completed.accuracy==3 && completed.profile==4
        && completed.rate==8000 && completed.samples>=1 && completed.samples<=64000
        && resetCompactState(completed);
}
Stream selectCompactEnsembleCandidate(const Stream& completed,const Pcm& reference,
    const Stream& proposal,const BitrateReport& search,CompactEnsembleReport& report,
    CandidateEvaluation* evaluation) {
    report=CompactEnsembleReport{};
    report.enabled=compactEnsembleEnabled();report.searchCandidates=search.candidates;
    report.searchSelected=search.selected;report.parameterTrials=search.parameterTrials;
    report.pulseTrials=search.pulseTrials;
    if(!validCompactModel(completed) || completed.accuracy!=3
        || reference.size()!=size_t(completed.samples)) {
        compactFailure(report,CompactInvalidIncumbent);return completed;
    }
    report.eligible=1;
    const auto original=packV9(completed);
    report.baselineBytes=report.selectedBytes=original.size();
    if(evaluation && !evaluation->matches(reference,8000,true,completed.qualityTarget)) {
        compactFailure(report,CompactSelectionFailure);return completed;
    }
    if(search.error) {compactFailure(report,CompactSearchFailure,search.error);return completed;}
    if(!validCompactModel(proposal) || proposal.accuracy!=4
        || proposal.qualityTarget!=completed.qualityTarget || proposal.samples!=completed.samples
        || (!completed.bright && proposal.bright)) {
        compactFailure(report,CompactInvalidCandidate);return completed;
    }
    const auto packed=packV9(proposal);report.rawBytes=packed.size();
    if(packed.empty() || packed.size()>original.size()) {
        compactFailure(report,CompactOverBudget);return completed;
    }
    const auto output=render(proposal);
    if(!verifyStream(proposal,output)) {
        compactFailure(report,CompactNativeMismatch);return completed;
    }
    report.rawValid=1;report.rawChanged=packed!=original;
    if(!report.rawChanged) {report.status=CompactUnchanged;return completed;}
    if(!stableLpcStream(proposal) || !safeSynthesisLevel(proposal,reference,output)
        || !safeSynthesisSpectrum(reference,output)) {
        compactFailure(report,CompactUnsafeCandidate);return completed;
    }
    auto selected=selectQualityProposals(completed,reference,{&proposal},report.selection,
        true,original.size(),evaluation);
    if(report.selection.error) {
        compactFailure(report,CompactSelectionFailure,report.selection.error);return completed;
    }
    const auto selectedBytes=packV9(selected);
    if(selectedBytes!=original && selectedBytes!=packed) {
        compactFailure(report,CompactSelectionFailure);return completed;
    }
    report.selected=selectedBytes!=original;
    report.selectedBytes=selectedBytes.size();
    report.status=report.selected?CompactSelected:CompactRejected;
    return selected;
}
Stream refineCompactEnsemble(const Stream& completed,const Pcm& reference,
    CompactEnsembleReport& report,CandidateEvaluation* evaluation,Stream* rawProposal) {
    report=CompactEnsembleReport{};report.enabled=compactEnsembleEnabled();
    if(rawProposal==&completed) {compactFailure(report,CompactInvalidIncumbent);return completed;}
    if(rawProposal)*rawProposal=Stream{};
    if(!report.enabled) {report.status=CompactDisabled;return completed;}
    if(!compactEnsembleEligible(completed,4,nullptr)) {report.status=CompactIneligible;return completed;}
    report.eligible=1;report.attempted=1;
    if(!validCompactModel(completed) || reference.size()!=size_t(completed.samples)) {
        compactFailure(report,CompactInvalidIncumbent);return completed;
    }
    if(evaluation && !evaluation->matches(reference,8000,true,completed.qualityTarget)) {
        compactFailure(report,CompactSelectionFailure);return completed;
    }
    const auto original=packV9(completed);const auto before=render(completed);
    report.baselineBytes=report.selectedBytes=original.size();
    Stream incumbent=completed;incumbent.accuracy=4;
    Stream prefix=completed;prefix.accuracy=4;
    if(packV9(incumbent)!=original || packV9(prefix)!=original
        || render(incumbent)!=before || render(prefix)!=before
        || !verifyStream(completed,before)) {
        compactFailure(report,CompactRelabelMismatch);return completed;
    }
    BitrateReport search;report.searchCalls=1;
    const auto proposal=encodeThreeK(reference,original.size(),search,.97,
        &incumbent,&prefix,completed.qualityTarget);
    auto selected=selectCompactEnsembleCandidate(completed,reference,proposal,search,report,evaluation);
    report.attempted=1;report.searchCalls=1;
    if(rawProposal && report.rawValid)*rawProposal=proposal;
    return selected;
}
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
Stream encodeAccuracy(const Pcm& reference,int level,int rate,AdaptiveReport& report,int calls,const Stream* prefix,QualityTarget target,Stream* compactRawProposal){
    report=AdaptiveReport{};const auto policy=accuracyPolicy(level);
    report.compactEnsemble.enabled=compactEnsembleEnabled();
    report.compactEnsemble.status=report.compactEnsemble.enabled?CompactIneligible:CompactDisabled;
    if(compactRawProposal && compactRawProposal==prefix){report.error=-1;return Stream{};}
    if(compactRawProposal)*compactRawProposal=Stream{};
    if(!validQualityTarget(target)||(prefix&&prefix->qualityTarget!=target)||!policy.level||reference.empty()||(rate!=8000&&rate!=12000&&rate!=16000)||calls<0||calls>4){report.error=-1;return Stream{};}
    Stream context=prefix?*prefix:Stream{};context.accuracy=level;context.qualityTarget=target;
    // One base model and one detail operator for every level and transport.
    // The exact bit budget decides how many ranked residual symbols survive.
    context.allowExtras=true;
    const int pre=context.continuation?context.pre:13926;
    SeedFitStatus seedStatus;
    const Stream seed=fitSeed(reference,policy.wireProfile,rate,pre,false,.97,&context,nullptr,&seedStatus,target);
    report.originalSeedStatus=seedStatus;
    Stream control=seed;
    if(control.samples!=int(reference.size())){report.error=-7;return Stream{};}
    control=canonicalAccuracy(control);
    const auto originalControl=control;
    const int budget=accuracyBudget(reference.size(),level,packV9(control).size());
    report.compactEnsemble.policyBudget=budget;
    auto corrected=refineAccuracyCorrections(control,reference,budget);
    if(packV9(corrected)!=packV9(control)) {
        const auto originalPcm=render(control),detailPcm=render(corrected);
        if(safeSynthesisLevel(corrected,reference,detailPcm)&&safeSynthesisSpectrum(reference,detailPcm)
            &&profileQualityAdmission(reference,originalPcm,detailPcm,rate,true,true,target))control=std::move(corrected);
    }
    if(!calls)return control;
    // Internal controller accounting is v5; independently enforce final V9
    // bytes below, including its header, flags, repeats and padding.
    CandidateEvaluation evaluation(reference,rate,true,target);
    auto optionalCompactPhase=[&](Stream& completed) {
#if LPX_ENCODER_COMPACT_ENSEMBLE && LPX_ENCODER_QUALITY_SEARCH && LPX_ENCODER_JOINT_REFINEMENT
        report.compactEnsemble.enabled=1;report.compactEnsemble.status=CompactIneligible;
        if(compactEnsembleEligible(completed,calls,prefix)) {
            auto selected=refineCompactEnsemble(completed,reference,report.compactEnsemble,&evaluation,compactRawProposal);
            completed=std::move(selected);
        }
#else
        (void)completed;
#endif
        report.compactEnsemble.policyBudget=budget;
    };
    Stream candidate=adaptiveEncode(reference,policy.wireProfile,rate,report,false,std::max(budget+9,compactBytes(seed)),calls,true,true,0,false,&context,&seed,&evaluation,target);
    report.originalSeedStatus=seedStatus;
    if(report.error==-6) {
        // The complete common control already fits this profile. Internal
        // legacy-v5 proposal accounting cannot invalidate that legal floor.
        report.error=0;report.cap=budget;report.selected=-1;
        optionalCompactPhase(control);return control;
    }
    if(report.error)return Stream{};
    candidate=canonicalAccuracy(candidate);
    // Retain the complete original admissible quantized control. All levels
    // share the same actual-rate, whole-output metric and octave guard.
    ProfileQualityReport selection;
    candidate=selectQualityProposals(originalControl,reference,{&control,&candidate},selection,true,budget,&evaluation);
    if(selection.error){report.error=selection.error;return Stream{};}
    if(!verifyStream(candidate,render(candidate))){report.error=-3;return Stream{};}
    optionalCompactPhase(candidate);
    return candidate;
}
}
