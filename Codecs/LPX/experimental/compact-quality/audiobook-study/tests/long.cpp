// New policy tests. The prior short-study helper source stays frozen.
#define main lpxFrozenRound2TestMain
#include "../../round2/tests/integration.cpp"
#undef main
#include "LpxStreaming.h"

namespace {
bool fullModelEqual(const Stream&a,const Stream&b) {
    return a.qualityTarget==b.qualityTarget&&a.samples==b.samples&&a.rate==b.rate&&a.profile==b.profile&&a.pre==b.pre&&a.bright==b.bright
      &&a.accuracy==b.accuracy&&a.spectra==b.spectra&&a.parameters==b.parameters&&a.pulses==b.pulses&&a.extras==b.extras
      &&a.continuation==b.continuation&&a.allowExtras==b.allowExtras&&a.previousSpectrum==b.previousSpectrum
      &&a.previousInput==b.previousInput&&a.previousCoefficients==b.previousCoefficients&&a.lookahead==b.lookahead
      &&a.initial.dd==b.initial.dd&&a.initial.cc==b.initial.cc&&std::equal(a.initial.h,a.initial.h+10,b.initial.h)
      &&std::equal(a.initial.ring,a.initial.ring+256,b.initial.ring);
}
void profileFields(std::ostream& t,const ProfileQualityReport&r){t<<r.candidates<<' '<<r.accepted<<' '<<r.error<<' '<<r.octaveRejected<<' '
 <<r.bandwidthCandidates<<' '<<r.localEvaluations<<' '<<r.fullEvaluations<<' '<<r.spectralLocalEvaluations<<' '<<r.spectralProposals<<' '
 <<r.spectralRegions<<' '<<r.initialObjective<<' '<<r.finalObjective<<' ';}
std::string legacyFields(const AdaptiveReport&r) {
    std::ostringstream t;t<<std::setprecision(17)<<r.candidates<<' '<<r.stages<<' '<<r.selected<<' '<<r.cap<<' '<<r.gainExponent<<' '<<r.error<<' '
      <<int(r.originalSeedStatus)<<' '<<r.expandedLocalEvaluations<<' '<<r.expandedFullEvaluations<<' '<<r.expandedAccepted<<' ';
    for(int x:r.stageOperator)t<<x<<' ';for(int x:r.localEvaluations)t<<x<<' ';for(int x:r.fullEvaluations)t<<x<<' ';
    for(const auto* m:{&r.baseline,&r.measurement}){t<<int(m->quality.target)<<' '<<m->clipped<<' '<<m->score<<' ';
        for(int p=0;p<2;++p)t<<m->quality.error[p]<<' '<<m->quality.stoi[p]<<' '<<m->diagnostic[p].within<<' '<<m->diagnostic[p].collapsed<<' '
          <<m->diagnostic[p].period<<' '<<m->diagnostic[p].shape<<' '<<m->voice[p]<<' '<<m->noise[p]<<' ';}
    const auto&l=r.loudness;t<<l.status<<' '<<l.limited<<' '<<l.gainLimited<<' '<<l.input<<' '<<l.prepared<<' '<<l.decoded<<' '<<l.gainDb<<' '<<l.factor<<' ';
    profileFields(t,r.qualitySearch);profileFields(t,r.jointQuality.selection);const auto&j=r.jointQuality;
    t<<j.headerLocalEvaluations<<' '<<j.headerFullEvaluations<<' '<<j.lpcRuns<<' '<<j.lpcProposals<<' '<<j.lpcBundles<<' '
     <<j.lpcSpectralEvaluations<<' '<<j.lpcPulseEvaluations<<' '<<j.lpcSynthesizedSamples;return t.str();
}
std::string completeFingerprint(const Stream&s,const AdaptiveReport&r) {
    uint64_t h=1469598103934665603ull;const auto b=packV9(s);h=hashBytes(h,b.data(),b.size());const auto text=legacyFields(r);h=hashBytes(h,text.data(),text.size());
    for(const auto&v:s.spectra)h=hashBytes(h,v.data(),sizeof(int)*10);for(const auto&v:s.parameters)h=hashBytes(h,v.data(),sizeof(int)*3);
    for(const auto&v:s.pulses)h=hashBytes(h,v.data(),sizeof(int)*2);for(const auto&v:s.extras)h=hashBytes(h,v.data(),sizeof(int)*2);
    const int fields[]={s.samples,s.rate,s.profile,s.pre,s.bright,s.accuracy,int(s.qualityTarget),s.continuation,s.allowExtras,s.initial.dd,s.initial.cc};
    h=hashBytes(h,fields,sizeof(fields));h=hashBytes(h,s.initial.h,sizeof(s.initial.h));h=hashBytes(h,s.initial.ring,sizeof(s.initial.ring));
    h=hashBytes(h,s.previousSpectrum.data(),sizeof(int)*10);h=hashBytes(h,s.previousInput.data(),sizeof(int16_t)*172);
    for(const auto&v:s.previousCoefficients)h=hashBytes(h,v.data(),sizeof(int16_t)*10);h=hashBytes(h,s.lookahead.data(),s.lookahead.size()*2);
    std::ostringstream t;t<<std::hex<<h;return t.str();
}
uint32_t little(const std::vector<uint8_t>& b,int at,int width){uint32_t v=0;for(int i=0;i<width;++i)v|=uint32_t(b[at+i])<<(8*i);return v;}
void headerCheck(const std::vector<uint8_t>& b,int samples) {
    const bool wide=samples>64000;const int h=wide?17:13;
    need(b.size()>size_t(h)&&b[0]=='L'&&b[1]=='9'&&bool(b[2]&64)==wide,"actual Long flag/header");
    need(little(b,3,2)==8000&&little(b,5,wide?4:2)==uint32_t(samples),"actual sample count high words");
    need(little(b,wide?13:11,wide?4:2)==b.size()-h,"actual complete payload width/length");
}
Pcm longNative(const Stream& stream) {
    const auto b=packV9(stream);headerCheck(b,stream.samples);const auto model=render(stream);Lpx4HybridCore d;
    need(d.beginWideV9(b.data(),uint32_t(b.size()))&&d.samples()==uint32_t(stream.samples)&&d.sampleRate()==8000
        &&d.produced()==0&&!d.error(),"wide begin metadata/reset progress");
    Pcm out(stream.samples);
    for(int i=0;i<stream.samples;++i){need(d.nextS16(out[i])&&out[i]==model[i],"continuous Long native/model PCM");
        if(i==65534||i==65535||i+1==stream.samples)need(d.produced()==uint32_t(i+1),"wide produced counter");}
    int16_t last;need(!d.nextS16(last)&&d.finished()&&!d.error()&&d.produced()==uint32_t(stream.samples),"Long PCM complete EOF");
    need(d.beginWideV9(b.data(),uint32_t(b.size()))&&d.produced()==0,"Long restart clears state");
    for(int value:out){uint8_t actual;int q14=(value+1)>>1;int expected=std::max(0,std::min(255,128+((q14*130+8192)>>14)));
        need(d.next(actual)&&actual==expected,"Long static PWM exact");}
    uint8_t tail;need(!d.next(tail)&&d.finished()&&!d.error()&&d.produced()==uint32_t(stream.samples),"Long PWM complete EOF");return out;
}
int longGeometry() {
    int cases=0;
    for(auto target:{QualityTarget::Pcm,QualityTarget::Pwm})for(int n:{64000,64001,65535,65536,128001,159999,160000,160001}) {
        auto s=fixture(n,target);longNative(s);auto fine=s;fine.accuracy=4;
        need(packV9(s)==packV9(fine)&&render(s)==render(fine),"Long physical relabel");++cases;
    }
    auto enhanced=fixture(128001,QualityTarget::Pcm);enhanced.extras[0]={{0,1}};
    need(packV9(enhanced)[2]&128,"enhanced Long flag");longNative(enhanced);++cases;
    // Outside the optional search scope: a real payload crossing uint16_t.
    const auto stress=fixture(1600000,QualityTarget::Pcm);const auto b=packV9(stress);
    need(b.size()-17>65535,"large-payload stress must exercise high payload bits");longNative(stress);++cases;
    Lpx4HybridCore d;need(!d.begin(b.data(),uint16_t(b.size())),"narrow input-size entry must not accept a truncated large payload size");
    auto valid=packV9(fixture(128001,QualityTarget::Pcm));int malformed=0;
    for(int which=0;which<5;++which){auto bad=valid;
        if(which==0)bad.resize(16);if(which==1)bad.pop_back();if(which==2)bad.push_back(0);
        if(which==3)std::fill(bad.begin()+5,bad.begin()+9,0);if(which==4)bad[13]^=1;
        need(!d.beginWideV9(bad.data(),uint32_t(bad.size()))&&d.error()&&!d.finished(),"malformed Long header/payload geometry");++malformed;
        need(d.beginWideV9(valid.data(),uint32_t(valid.size()))&&d.produced()==0&&!d.error(),"valid restart after malformed Long");}
    std::cout<<"PASS geometry: "<<cases<<" continuous native PCM/PWM/EOF cases; five malformed headers; real payload above65535 bytes\n";return 0;
}
int longScope(int maximum) {
    int checks=0;
    for(auto target:{QualityTarget::Pcm,QualityTarget::Pwm}){
        auto s=fixture(641,target);
        for(int n:{0,1,64000,64001,65535,65536,128001,159999,160000,160001}){
            auto trial=s;trial.samples=n;need(compactEnsembleEligible(trial,4)==(n>=1&&n<=maximum),"paired length scope");++checks;}
        s.samples=128001;
        for(int calls:{-1,0,1,2,3,5}){need(!compactEnsembleEligible(s,calls),"calls exclusion");++checks;}
        auto reset=s;need(!compactEnsembleEligible(s,4,&reset),"nonnull first-window reset prefix exclusion");++checks;
        reset.continuation=true;need(!compactEnsembleEligible(s,4,&reset),"nonnull continuation prefix exclusion");++checks;
        const std::vector<std::function<void(Stream&)>> mutations={[](Stream&t){t.rate=12000;},[](Stream&t){t.rate=16000;},
            [](Stream&t){t.accuracy=4;},[](Stream&t){t.accuracy=6;},[](Stream&t){t.accuracy=8;},[](Stream&t){t.profile=6;},
            [](Stream&t){t.continuation=true;},[](Stream&t){t.initial.h[9]=1;},[](Stream&t){t.initial.ring[255]=1;},
            [](Stream&t){t.initial.dd=1;},[](Stream&t){t.initial.cc=1;},[](Stream&t){t.lookahead.push_back(0);},[](Stream&t){t.qualityTarget=QualityTarget(8);}};
        for(const auto& change:mutations){auto trial=s;change(trial);need(!compactEnsembleEligible(trial,4),"unchanged rate/policy/reset exclusion");++checks;}
        auto tooLong=fixture(160001,target);auto reference=render(tooLong);CompactEnsembleReport report;Stream raw=s;
        const auto kept=refineCompactEnsemble(tooLong,reference,report,nullptr,&raw);
        need(packV9(kept)==packV9(tooLong)&&raw.samples==0&&report.searchCalls==0&&report.attempted==0,"above-limit exact rollback/stale capture");++checks;
    }
    std::cout<<"PASS scope: "<<checks<<" paired boundaries and unchanged exclusions; above-limit exact rollback\n";return 0;
}
int longSelection() {
    int accepted=0,rollbacks=0;
    for(auto target:{QualityTarget::Pcm,QualityTarget::Pwm})for(int n:{64001,128001,160000}){
        auto base=fixture(n,target);const auto proposal=odd(base);const auto reference=longNative(proposal);const auto oldBytes=packV9(base);
        need(oldBytes.size()==17+little(oldBytes,13,4),"B0 includes17-byte Long header");
        BitrateReport search;search.candidates=7;search.parameterTrials=13;search.pulseTrials=17;CompactEnsembleReport report;
        ProfileQualityReport independent;auto expected=selectQualityProposals(base,reference,{&proposal},independent,true,oldBytes.size());
        auto actual=selectCompactEnsembleCandidate(base,reference,proposal,search,report);
        need(!independent.error&&packV9(expected)==packV9(proposal)&&packV9(actual)==packV9(proposal)&&actual.accuracy==4
            &&report.status==CompactSelected&&report.baselineBytes==int(oldBytes.size())&&report.selectedBytes<=report.baselineBytes,"Long odd-grid existing-selector selection/B0");++accepted;
        auto error=search;error.error=-6;actual=selectCompactEnsembleCandidate(base,reference,proposal,error,report);retained(actual,base);
        need(report.status==CompactSearchFailure&&report.error==-6&&report.parameterTrials==13,"Long independent failure report");++rollbacks;
        auto growth=proposal;growth.extras[0]={{0,1}};need(packV9(growth).size()>oldBytes.size(),"Long growth fixture");
        actual=selectCompactEnsembleCandidate(base,reference,growth,search,report);retained(actual,base);need(report.status==CompactOverBudget,"Long actual B0 growth guard");++rollbacks;
        auto empty=proposal;empty.pulses.clear();actual=selectCompactEnsembleCandidate(base,reference,empty,search,report);retained(actual,base);
        need(report.status==CompactInvalidCandidate,"Long malformed rollback");++rollbacks;
        CandidateEvaluation wrong(reference,8000,true,target==QualityTarget::Pcm?QualityTarget::Pwm:QualityTarget::Pcm);
        actual=selectCompactEnsembleCandidate(base,reference,proposal,search,report,&wrong);retained(actual,base);need(report.status==CompactSelectionFailure,"Long target context mismatch");++rollbacks;
    }
    std::cout<<"PASS selection: "<<accepted<<" genuine Long odd-grid selections; "<<rollbacks<<" actual-B0/error/context rollbacks\n";return 0;
}
int longAutomatic(int maximum) {
    int cases=0;
    for(auto target:{QualityTarget::Pcm,QualityTarget::Pwm})for(int n:{641,128001}) {
        Pcm reference(n,0);need(enc_reserve(n)>0,"Long host workspace reserve");AdaptiveReport report;Stream raw=fixture(41,target);
        const auto selected=encodeAccuracy(reference,3,8000,report,4,nullptr,target,&raw);
        need(!report.error&&selected.samples==n,"full synthetic Long encode");longNative(selected);
        const bool active=compactEnsembleEnabled()&&n<=maximum;
        need(report.compactEnsemble.attempted==int(active)&&report.compactEnsemble.searchCalls==int(active),"automatic length-specific phase count");
        if(!active)need(raw.samples==0,"skipped Long raw capture stale");
        std::cout<<"ENCODE "<<n<<' '<<int(target)<<' '<<fingerprint(selected,report)<<'\n';++cases;
        // Actual C ABI final packing, including the32-bit sample count.
        std::copy(reference.begin(),reference.end(),enc_input());const int size=enc_accuracy_target(n,3,8000,4,0,-18,24,int(target));
        need(size>0&&std::vector<uint8_t>(enc_adaptive_output(),enc_adaptive_output()+size)==packV9(selected),"Long C ABI final pack");++cases;
    }
    std::cout<<"PASS automatic: "<<cases<<" complete synthetic host/C-ABI encodes at short and Long lengths\n";return 0;
}
int longStreaming() {
    const int n=65536;int cases=0;
    for(auto target:{QualityTarget::Pcm,QualityTarget::Pwm}){
        auto source=render(fixture(n,target));StreamingEncoder encoder(n,3,8000,0,4,false,true,target);
        need(!encoder.status(),"stream setup");std::vector<uint8_t> a,b;Pcm control,candidate;
        for(int at=0;at<n;at+=kLpxStreamWindow){int stop=std::min(n,at+kLpxStreamWindow);Pcm input(source.begin()+at,source.begin()+stop),future;
            if(stop<n)future.assign(source.begin()+stop,source.begin()+std::min(n,stop+48));StreamingChunk chunk;
            need(encoder.process(input,future,chunk)>=0,"real streaming window process");
            a.insert(a.end(),chunk.controlBytes.begin(),chunk.controlBytes.end());b.insert(b.end(),chunk.candidateBytes.begin(),chunk.candidateBytes.end());
            control.insert(control.end(),chunk.controlPcm.begin(),chunk.controlPcm.end());candidate.insert(candidate.end(),chunk.candidatePcm.begin(),chunk.candidatePcm.end());}
        StreamingChunk tail;need(encoder.finish(tail)>=0,"stream finish");a.insert(a.end(),tail.controlBytes.begin(),tail.controlBytes.end());
        b.insert(b.end(),tail.candidateBytes.begin(),tail.candidateBytes.end());auto header=encoder.getHeader(false);a.insert(a.begin(),header.begin(),header.end());headerCheck(a,n);
        Lpx4HybridCore decoder;need(decoder.beginWideV9(a.data(),a.size()),"assembled streaming Long begin");
        for(int expected:control){int16_t value;need(decoder.nextS16(value)&&value==expected,"carried streaming control/native PCM");}
        int16_t last;need(!decoder.nextS16(last)&&decoder.finished()&&!decoder.error()&&decoder.produced()==uint32_t(n),"assembled control EOF");
        uint64_t h=hashBytes(1469598103934665603ull,a.data(),a.size());
        if(encoder.hasCandidate()){header=encoder.getHeader(true);b.insert(b.begin(),header.begin(),header.end());headerCheck(b,n);
            need(decoder.beginWideV9(b.data(),b.size()),"assembled candidate Long begin");for(int expected:candidate){int16_t value;need(decoder.nextS16(value)&&value==expected,"carried candidate/native PCM");}
            need(!decoder.nextS16(last)&&decoder.finished()&&!decoder.error()&&decoder.produced()==uint32_t(n),"assembled candidate EOF");h=hashBytes(h,b.data(),b.size());}
        std::cout<<"STREAM "<<int(target)<<' '<<std::hex<<h<<std::dec<<'\n';++cases;
    }
    std::cout<<"PASS streaming: "<<cases<<" genuine multi-window nonzero carried-state Long streams and terminal tail; optional phase remains excluded\n";return 0;
}
int longComposition(int maximum) {
    int cases=0;
    for(auto target:{QualityTarget::Pcm,QualityTarget::Pwm})for(int n:{1281,128001}) {
        Pcm reference=render(fixture(n,target));for(auto&v:reference)v/=8;
        need(enc_reserve(n)>0,"composition workspace reserve");Stream reset;reset.qualityTarget=target;const auto resetBefore=reset;
        AdaptiveReport baselineReport,automaticReport;Stream raw;
        const auto baseline=encodeAccuracy(reference,3,8000,baselineReport,4,&reset,target);
        need(!baselineReport.error&&baseline.samples==n&&fullModelEqual(reset,resetBefore),"fresh reset-prefix complete floor");
        need(!baselineReport.compactEnsemble.attempted&&!baselineReport.compactEnsemble.searchCalls,"nonnull reset baseline must skip optional phase");
        const auto legacyBefore=legacyFields(baselineReport);CompactEnsembleReport stage;Stream composed=baseline;
        if(compactEnsembleEnabled()&&n<=maximum)composed=refineCompactEnsemble(baseline,reference,stage,nullptr,&raw);
        const auto automatic=encodeAccuracy(reference,3,8000,automaticReport,4,nullptr,target);
        need(!automaticReport.error&&fullModelEqual(composed,automatic)&&packV9(composed)==packV9(automatic)
            &&longNative(composed)==longNative(automatic),"automatic and direct composition differ");
        need(legacyFields(automaticReport)==legacyBefore&&legacyFields(baselineReport)==legacyBefore,"optional composition overwrote legacy report");
        if(!compactEnsembleEnabled())need(fullModelEqual(automatic,baseline),"macro0 reset-prefix and null-prefix complete model mismatch");
        if(compactEnsembleEnabled()&&n<=maximum)need(stage.searchCalls==1&&automaticReport.compactEnsemble.searchCalls==1
          &&stage.status==automaticReport.compactEnsemble.status&&stage.rawBytes==automaticReport.compactEnsemble.rawBytes
          &&stage.selectedBytes==automaticReport.compactEnsemble.selectedBytes,"direct/automatic optional stage mismatch");
        std::cout<<"FLOOR "<<n<<' '<<int(target)<<' '<<completeFingerprint(baseline,baselineReport)<<'\n';
        std::cout<<"COMPOSE "<<n<<' '<<int(target)<<' '<<completeFingerprint(composed,automaticReport)<<'\n';++cases;
    }
    std::cout<<"PASS composition: "<<cases<<" nonzero synthetic short/Long reset-prefix floors and complete automatic/direct-model/report/PCM equivalence\n";return 0;
}
}
int main(int argc,char**argv){need(argc==3,"mode and expected policy limit");const std::string mode=argv[1];const int maximum=std::atoi(argv[2]);
    if(mode=="geometry")return longGeometry();if(mode=="scope")return longScope(maximum);if(mode=="selection")return longSelection();
    if(mode=="automatic")return longAutomatic(maximum);if(mode=="streaming")return longStreaming();if(mode=="composition")return longComposition(maximum);return 2;}
