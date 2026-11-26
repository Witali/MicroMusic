// Independent synthetic integration gate. No speech corpus or AVR claims.
#include "LpxAccuracy.h"
#include "LpxBitrateProfiles.h"
#include "LpxCandidateEvaluation.h"
#include "LpxEncoder.h"
#include "Lpx4HybridCore.h"
#include <algorithm>
#include <cstdlib>
#include <functional>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <string>
using namespace lpx;
extern "C" uint8_t* enc_adaptive_output();

namespace {
void need(bool ok,const char* why){if(!ok){std::cerr<<"FAIL: "<<why<<'\n';std::exit(1);}}
Pcm native(const Stream& stream) {
    const auto bytes=packV9(stream);Lpx4HybridCore d;
    need(d.beginWideV9(bytes.data(),bytes.size()),"native begin");Pcm pcm(d.samples());
    for(auto& value:pcm)need(d.nextS16(value),"native PCM length");
    int16_t tail;need(!d.nextS16(tail)&&d.finished()&&!d.error(),"native PCM EOF");
    need(d.beginWideV9(bytes.data(),bytes.size()),"native PWM begin");
    for(int value:pcm){uint8_t duty;const int q14=(value+1)>>1;
        const int expected=std::max(0,std::min(255,128+((q14*130+8192)>>14)));
        need(d.next(duty)&&duty==expected,"native PWM transfer");}
    uint8_t tailDuty;need(!d.next(tailDuty)&&d.finished()&&!d.error(),"native PWM EOF");
    need(pcm==render(stream),"model/native PCM identity");return pcm;
}
Stream fixture(int n,QualityTarget target) {
    Stream s;s.samples=n;s.rate=8000;s.profile=4;s.accuracy=3;s.qualityTarget=target;s.pre=8192;
    Spectrum v;for(int j=0;j<10;++j)v[j]=2+3*j;
    const int frames=(n+319)/320;s.spectra.assign(frames,v);s.parameters.assign(frames*2,Parameters{{16,37,6}});
    s.pulses.resize(frames*16);s.extras.assign(frames*8,Pulse{{-1,0}});
    for(int p=0;p<frames*16;++p){int pos=(p*7)%20;if(pos%5==2)++pos;s.pulses[p]={{pos,p%2?-8:8}};}
    s=canonicalAccuracy(s);return s;
}
Stream odd(const Stream& s){auto out=s;out.accuracy=4;for(auto& v:out.spectra)++v[0];return out;}
void retained(const Stream& selected,const Stream& original) {
    need(selected.accuracy==original.accuracy&&selected.qualityTarget==original.qualityTarget
        &&packV9(selected)==packV9(original)&&render(selected)==render(original),"exact original floor rollback");
}
uint64_t hashBytes(uint64_t h,const void* data,size_t n){auto p=static_cast<const uint8_t*>(data);while(n--){h^=*p++;h*=1099511628211ull;}return h;}
std::string fingerprint(const Stream& s,const AdaptiveReport& report) {
    uint64_t h=1469598103934665603ull;const auto bytes=packV9(s);const auto pcm=native(s);
    h=hashBytes(h,bytes.data(),bytes.size());h=hashBytes(h,pcm.data(),pcm.size()*2);
    // Explicit old accounting only: the new optional report is independent.
    const int old[]={report.candidates,report.stages,report.selected,report.cap,report.gainExponent,report.error,
        int(report.originalSeedStatus),report.expandedLocalEvaluations,report.expandedFullEvaluations,report.expandedAccepted,
        report.qualitySearch.candidates,report.qualitySearch.accepted,report.qualitySearch.error,
        report.jointQuality.selection.candidates,report.jointQuality.selection.accepted,report.jointQuality.selection.error,
        report.jointQuality.lpcRuns,report.jointQuality.lpcProposals,report.jointQuality.lpcBundles};
    h=hashBytes(h,old,sizeof(old));h=hashBytes(h,report.stageOperator,sizeof(report.stageOperator));
    h=hashBytes(h,report.localEvaluations,sizeof(report.localEvaluations));h=hashBytes(h,report.fullEvaluations,sizeof(report.fullEvaluations));
    std::ostringstream text;text<<std::hex<<h;return text.str();
}
int identity() {
    int count=0;
    for(auto target:{QualityTarget::Pcm,QualityTarget::Pwm})for(int n:{1,19,20,21,39,40,41,159,160,161,319,320,321,641,1281}) {
        const auto base=fixture(n,target);auto fine=base;fine.accuracy=4;
        need(packV9(base)==packV9(fine)&&native(base)==native(fine),"physical P3 relabel changed output");
        const auto candidate=odd(base);need(packV9(candidate).size()<=packV9(base).size(),"odd fixture over B0");
        need(native(candidate)==render(candidate),"odd-rank native output");
        auto wrong=candidate;wrong.accuracy=3;
        need(packV9(wrong)!=packV9(candidate),"odd fixture does not expose wire requantization");
        if(n>=41)need(render(wrong)!=render(candidate),"odd fixture does not expose audio requantization");++count;
    }
    std::cout<<"PASS identity: "<<count<<" reset/partial-tail relabel and odd-rank PCM/PWM/EOF cases\n";return 0;
}
int eligibility() {
    int count=0;
    for(auto target:{QualityTarget::Pcm,QualityTarget::Pwm}) {
        auto base=fixture(641,target);need(compactEnsembleEligible(base,4),"ordinary P3 eligibility");
        for(int calls:{0,1,2,3,5,-1}){need(!compactEnsembleEligible(base,calls),"call-count exclusion");++count;}
        auto prefix=base;need(!compactEnsembleEligible(base,4,&prefix),"nonnull reset prefix exclusion");++count;
        prefix.continuation=true;need(!compactEnsembleEligible(base,4,&prefix),"nonnull continuation prefix exclusion");++count;
        for(int rate:{12000,16000}){auto s=base;s.rate=rate;need(!compactEnsembleEligible(s,4),"rate exclusion");++count;}
        for(int level:{0,1,2,4,5,6,7,8}){auto s=base;s.accuracy=level;need(!compactEnsembleEligible(s,4),"accuracy exclusion");++count;}
        for(int n:{0,64001}){auto s=base;s.samples=n;need(!compactEnsembleEligible(s,4),"Long/empty exclusion");++count;}
        for(int n:{1,64000}){auto s=base;s.samples=n;need(compactEnsembleEligible(s,4),"sample boundary eligibility");++count;}
        const std::vector<std::function<void(Stream&)>> mutations={
            [](Stream&s){s.profile=6;},[](Stream&s){s.continuation=true;},[](Stream&s){s.initial.dd=1;},
            [](Stream&s){s.initial.cc=-1;},[](Stream&s){s.initial.h[9]=1;},[](Stream&s){s.initial.ring[255]=1;},
            [](Stream&s){s.lookahead.push_back(0);},[](Stream&s){s.qualityTarget=QualityTarget(7);}};
        for(const auto& mutate:mutations){auto s=base;mutate(s);need(!compactEnsembleEligible(s,4),"state/profile/target exclusion");++count;}
    }
    need(compactEnsembleEnabled()==bool(LPX_ENCODER_COMPACT_ENSEMBLE&&LPX_ENCODER_QUALITY_SEARCH&&LPX_ENCODER_JOINT_REFINEMENT),"explicit switch gate");
    std::cout<<"PASS eligibility: "<<count<<" source-independent scope and boundary checks\n";return 0;
}
int selection() {
    int rejected=0,accepted=0;
    for(auto target:{QualityTarget::Pcm,QualityTarget::Pwm}) {
        const auto base=fixture(1281,target);auto fine=base;fine.accuracy=4;const auto proposal=odd(base);
        const auto reference=native(proposal);BitrateReport search;search.candidates=7;search.selected=2;search.parameterTrials=13;search.pulseTrials=17;
        CompactEnsembleReport report;
        auto selected=selectCompactEnsembleCandidate(base,reference,fine,search,report);
        retained(selected,base);need(report.status==CompactUnchanged&&report.rawValid&&!report.rawChanged,"unchanged relabel settlement");
        for(int error:{-1,-2,-3,-6,-7,-1000}){auto failed=search;failed.error=error;
            selected=selectCompactEnsembleCandidate(base,reference,proposal,failed,report);retained(selected,base);
            need(report.status==CompactSearchFailure&&report.error==error&&report.searchCandidates==7
                &&report.searchSelected==2&&report.parameterTrials==13&&report.pulseTrials==17,"optional error metadata");++rejected;}
        const std::vector<std::function<void(Stream&)>> mutations={
            [](Stream&s){s.accuracy=3;},[](Stream&s){s.qualityTarget=s.qualityTarget==QualityTarget::Pcm?QualityTarget::Pwm:QualityTarget::Pcm;},
            [](Stream&s){--s.samples;},[](Stream&s){s.rate=12000;},[](Stream&s){s.profile=6;},
            [](Stream&s){s.spectra.clear();},[](Stream&s){s.parameters.clear();},[](Stream&s){s.pulses.clear();},[](Stream&s){s.extras.clear();},
            [](Stream&s){s.spectra[0][1]=s.spectra[0][0];},[](Stream&s){s.parameters[0][0]=32;},
            [](Stream&s){s.parameters[0][1]=17;},[](Stream&s){s.parameters[0][2]=3;},
            [](Stream&s){s.pulses[0]={{2,8}};},[](Stream&s){s.pulses[0]={{0,0}};},
            [](Stream&s){s.bright=1;},[](Stream&s){s.bright=11470;},[](Stream&s){s.pre=16385;},
            [](Stream&s){s.continuation=true;},[](Stream&s){s.initial.dd=1;},[](Stream&s){s.lookahead.push_back(0);}};
        for(const auto& mutate:mutations){auto invalid=proposal;mutate(invalid);
            selected=selectCompactEnsembleCandidate(base,reference,invalid,search,report);retained(selected,base);
            need(report.status==CompactInvalidCandidate&&!report.rawValid,"malformed native/policy/geometry or brightness accepted");++rejected;}
        auto growing=proposal;growing.extras[0]={{0,1}};need(packV9(growing).size()>packV9(base).size(),"growth fixture");
        selected=selectCompactEnsembleCandidate(base,reference,growing,search,report);retained(selected,base);
        need(report.status==CompactOverBudget,"actual B0 not enforced");++rejected;
        CandidateEvaluation mismatch(reference,8000,true,target==QualityTarget::Pcm?QualityTarget::Pwm:QualityTarget::Pcm);
        selected=selectCompactEnsembleCandidate(base,reference,proposal,search,report,&mismatch);retained(selected,base);
        need(report.status==CompactSelectionFailure,"foreign target cache accepted");++rejected;
        auto other=reference;other[0]^=1;CandidateEvaluation foreign(other,8000,true,target);
        selected=selectCompactEnsembleCandidate(base,reference,proposal,search,report,&foreign);retained(selected,base);
        need(report.status==CompactSelectionFailure,"foreign reference cache accepted");++rejected;
        CandidateEvaluation matching(reference,8000,true,target);ProfileQualityReport oracleReport;
        const auto oracle=selectQualityProposals(base,reference,{&proposal},oracleReport,true,packV9(base).size(),&matching);
        selected=selectCompactEnsembleCandidate(base,reference,proposal,search,report,&matching);
        need(!oracleReport.error&&packV9(oracle)==packV9(proposal),"positive fixture not accepted by unchanged selector");
        need(report.status==CompactSelected&&report.selected&&report.rawValid&&report.rawChanged
            &&selected.accuracy==4&&packV9(selected)==packV9(proposal)&&native(selected)==reference,"selected fine output requantized or lost");++accepted;
        // A zero-error finished floor cannot be displaced by a nonexact proposal.
        const auto floorReference=native(base);
        selected=selectCompactEnsembleCandidate(base,floorReference,proposal,search,report);retained(selected,base);
        need(report.status==CompactRejected||report.status==CompactUnsafeCandidate,"regression not rejected by old admission");++rejected;
        auto invalidBase=base;invalidBase.accuracy=4;
        selected=selectCompactEnsembleCandidate(invalidBase,reference,proposal,search,report);retained(selected,invalidBase);
        need(report.status==CompactInvalidIncumbent,"invalid finished floor accepted");++rejected;
        selected=selectCompactEnsembleCandidate(base,Pcm(1280),proposal,search,report);retained(selected,base);
        need(report.status==CompactInvalidIncumbent,"reference length mismatch");++rejected;
        // Aliased diagnostic capture must not erase the immutable input.
        auto aliased=base;const auto aliasBytes=packV9(aliased);
        selected=refineCompactEnsemble(aliased,reference,report,nullptr,&aliased);
        need(packV9(aliased)==aliasBytes&&packV9(selected)==aliasBytes&&report.status==CompactInvalidIncumbent,"aliased raw capture changed floor");++rejected;
        auto stale=proposal;auto ineligible=base;ineligible.continuation=true;
        selected=refineCompactEnsemble(ineligible,reference,report,nullptr,&stale);
        need(stale.samples==0&&packV9(selected)==packV9(ineligible)&&report.searchCalls==0,"skipped capture retained stale proposal");++rejected;
    }
    std::cout<<"PASS selection: "<<accepted<<" real old-selector odd-rank acceptances and "<<rejected<<" rollback/cache/guard cases\n";return 0;
}
int automatic() {
    int cases=0;
    for(auto target:{QualityTarget::Pcm,QualityTarget::Pwm}) {
        const auto reference=native(fixture(41,target));
        need(enc_reserve(reference.size())>0,"host seed workspace reserve");
        auto run=[&](int level,int rate,int calls,const Stream* prefix,const std::string& label,bool active){
            AdaptiveReport report;Stream raw=fixture(41,target);
            const auto selected=encodeAccuracy(reference,level,rate,report,calls,prefix,target,&raw);
            need(!report.error&&selected.samples==41,"synthetic complete encode failed");
            need(report.compactEnsemble.enabled==int(compactEnsembleEnabled()),"skipped-call capability reporting");
            if(active&&compactEnsembleEnabled())need(report.compactEnsemble.attempted==1&&report.compactEnsemble.searchCalls==1,"automatic stage did not run exactly once");
            else need(report.compactEnsemble.attempted==0&&report.compactEnsemble.searchCalls==0&&raw.samples==0
                &&report.compactEnsemble.status==(compactEnsembleEnabled()?CompactIneligible:CompactDisabled),"excluded/disabled automatic stage ran or leaked raw/status");
            need(report.compactEnsemble.policyBudget>=int(packV9(selected).size()),"final policy bound");
            if(!active)std::cout<<"EXCLUDED "<<int(target)<<' '<<label<<' '<<fingerprint(selected,report)<<'\n';
            else std::cout<<"ACTIVE "<<int(target)<<' '<<fingerprint(selected,report)<<' '<<report.compactEnsemble.searchCalls<<'\n';
            ++cases;return selected;
        };
        for(int calls=0;calls<4;++calls)run(3,8000,calls,nullptr,"calls"+std::to_string(calls),false);
        for(int level:{4,6,8})run(level,8000,4,nullptr,"level"+std::to_string(level),false);
        for(int rate:{12000,16000})run(3,rate,4,nullptr,"rate"+std::to_string(rate),false);
        const auto prefix=fixture(41,target);run(3,8000,4,&prefix,"nonnull-reset",false);
        const auto selected=run(3,8000,4,nullptr,"eligible",true);
        need(enc_reserve(reference.size())>=0,"C ABI reserve");std::copy(reference.begin(),reference.end(),enc_input());
        const int size=enc_accuracy_target(reference.size(),3,8000,4,0,-18,24,int(target));
        need(size>0,"C ABI complete encode");const std::vector<uint8_t> actual(enc_adaptive_output(),enc_adaptive_output()+size);
        need(actual==packV9(selected),"C ABI final pack disagrees with selected stream");native(selected);++cases;
        // Raw capture aliasing an external prefix is rejected before mutation.
        auto alias=prefix;AdaptiveReport report;const auto before=packV9(alias);
        const auto invalid=encodeAccuracy(reference,3,8000,report,4,&alias,target,&alias);
        need(report.error==-1&&invalid.samples==0&&packV9(alias)==before,"prefix/raw alias corrupted immutable context");++cases;
    }
    std::cout<<"PASS automatic: "<<cases<<" complete synthetic encodes/C ABI/alias cases; no speech or continuation-support claim\n";return 0;
}
}
int main(int argc,char**argv){need(argc==2,"select identity, eligibility, selection or automatic");const std::string mode=argv[1];
    if(mode=="identity")return identity();if(mode=="eligibility")return eligibility();if(mode=="selection")return selection();if(mode=="automatic")return automatic();return 2;}
