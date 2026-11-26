// Reuse the frozen independent full-native oracle without editing its tests.
#define main frozen_local_trace_main
#include "local_trace.cpp"
#undef main
#include <functional>
#include <limits>

namespace {
using namespace lpx;
Stream neighborFixture(int n,int level,int rate) {
    auto s=fixture(n,level,rate);
    Spectrum a={{0,1,2,3,8,13,14,19,24,29}};
    if(s.profile==6)for(int j=0;j<10;++j)a[j]=3+5*j;
    for(int f=0;f<int(s.spectra.size());++f) {
        s.spectra[f]=a;
        if(f%5==2||f%5==3)s.spectra[f][7]+=s.profile==4?4:2;
    }
    return canonicalAccuracy(s);
}
bool ordered(const Spectrum& s,int profile) {
    for(int i=0;i<10;++i)if(s[i]<0||s[i]>=(profile==4?32:64)||(i&&s[i]<=s[i-1]))return false;
    return true;
}
Stream edit(const Stream& base,int first,int last,int distance) {
    Stream s=base;
    for(int f=first;f<last;++f)s.spectra[f][4]+=distance;
    return s;
}
int composeContracts() {
    int accepted=0,rejected=0;
    for(int rate:{8000,12000,16000})for(QualityTarget target:{QualityTarget::Pcm,QualityTarget::Pwm}) {
        auto base=neighborFixture(1601,3,rate);base.qualityTarget=target;
        const int cap=10000;const auto original=packV9(base);
        for(int distance:{-4,-2,2,4}) {
            auto a=edit(base,0,2,distance),b=edit(base,2,4,-distance);
            need(ordered(a.spectra[0],4)&&ordered(b.spectra[2],4),"legal composable fixture is unordered");
            auto bundles=composeLpcRuns(base,{a,b},{1.,2.},cap,true);
            need(bundles.size()==1,"legal P3 magnitude2/4 singles were not composable");
            auto expected=base;
            std::copy(a.spectra.begin(),a.spectra.begin()+2,expected.spectra.begin());
            std::copy(b.spectra.begin()+2,b.spectra.begin()+4,expected.spectra.begin()+2);
            need(bundles[0].spectra==expected.spectra&&packV9(bundles[0])==packV9(expected),"composer did not retain exact legal raw edits");
            unchanged(base,bundles[0]);native(bundles[0]);++accepted;
        }
        auto good=edit(base,2,4,4),valid=edit(base,0,2,4);
        auto reject=[&](const Stream& bad) {
            need(composeLpcRuns(base,{bad,good},{1.,2.},cap,true).empty(),"invalid single participated in a bundle");++rejected;
        };
        for(int d:{-3,-1,1,3})reject(edit(base,0,2,d));
        auto bad=valid;bad.spectra[0][4]=13;bad.spectra[1][4]=13;reject(bad);
        bad=valid;for(int f=0;f<2;++f)bad.spectra[f][6]+=2;reject(bad);
        bad=valid;bad.spectra[1]=base.spectra[1];reject(bad);
        reject(edit(base,1,2,4));
        std::vector<std::function<void(Stream&)>> mutations={
            [](Stream&s){++s.samples;},[](Stream&s){s.rate=12001;},[](Stream&s){s.profile=6;},
            [](Stream&s){s.pre++;},[](Stream&s){s.bright++;},[](Stream&s){s.parameters[0][0]++;},
            [](Stream&s){s.extras[0]={{0,1}};},[](Stream&s){s.accuracy=4;},
            [](Stream&s){s.qualityTarget=s.qualityTarget==QualityTarget::Pcm?QualityTarget::Pwm:QualityTarget::Pcm;},
            [](Stream&s){s.continuation=true;},[](Stream&s){s.allowExtras=!s.allowExtras;},
            [](Stream&s){s.previousSpectrum[0]++;},[](Stream&s){s.previousInput[0]++;},
            [](Stream&s){s.previousCoefficients[0][0]++;},[](Stream&s){s.lookahead.push_back(0);},
            [](Stream&s){s.initial.h[0]++;},[](Stream&s){s.initial.ring[255]++;},
            [](Stream&s){s.initial.dd++;},[](Stream&s){s.initial.cc++;},
            [](Stream&s){s.spectra.pop_back();},[](Stream&s){s.pulses.pop_back();},
            [](Stream&s){s.pulses[8][1]*=-1;},[](Stream&s){s.pulses[0]={{2,8}};},
            [](Stream&s){s.pulses[0]={{0,0}};}
        };
        for(const auto& mutate:mutations){bad=valid;mutate(bad);reject(bad);}
        for(double score:{-1.,std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity()}) {
            need(composeLpcRuns(base,{valid,good},{score,2.},cap,true).empty(),"invalid score participated in a bundle");++rejected;
        }
        auto tail=edit(base,4,6,4);tail.pulses[81]={{0,8}};
        need(composeLpcRuns(base,{valid,tail},{1.,2.},cap,true).empty(),"unplayed tail pulse edit participated in a bundle");++rejected;
        need(composeLpcRuns(base,{valid,good},{1.,2.},int(original.size())-1,true).empty(),"over-budget anchor composed");++rejected;
        need(packV9(base)==original,"composer mutated its baseline");
    }
    std::printf("PASS composition: %d legal P3 magnitude2/4 bundles; %d illegal/multifield/context/score/tail/cap rejections\n",accepted,rejected);
    return 0;
}
int generatorContracts() {
    int cases=0,proposals=0,steps=0;
    for(int rate:{8000,12000,16000})for(QualityTarget target:{QualityTarget::Pcm,QualityTarget::Pwm}) {
        auto base=neighborFixture(641,3,rate);base.qualityTarget=target;
        // Odd non-extreme target cannot accidentally equal a saturated or
        // even-valued native sample in the one-sample final run.
        const Pcm reference(base.samples,12345);int expected=0;
        for(int first=0;first<int(base.spectra.size());) {
            int last=first+1;while(last<int(base.spectra.size())&&base.spectra[last]==base.spectra[first])++last;
            for(int field=0;field<10;++field)for(int d:{-4,-2,2,4}) {
                auto spectrum=base.spectra[first];spectrum[field]+=d;expected+=ordered(spectrum,4);
            }
            first=last;
        }
        const auto original=packV9(base);
        const auto result=proposeLpcRuns(base,reference,10000,true),again=proposeLpcRuns(base,reference,10000,true);
        if(result.spectralEvaluations!=uint64_t(expected))
            std::fprintf(stderr,"generator rate%d target%d expected%d actual%llu\n",rate,int(target),expected,
                         static_cast<unsigned long long>(result.spectralEvaluations));
        need(result.spectralEvaluations==uint64_t(expected),"generator did not evaluate the exact legal four-delta P3 neighborhood");
        need(result.runs<=4&&result.spectralEvaluations<=160&&result.proposals.size()<=8,"P3 generator exceeded registered bounds");
        need(result.proposals.size()==again.proposals.size()&&result.spectralEvaluations==again.spectralEvaluations
            &&result.pulseEvaluations==again.pulseEvaluations&&result.synthesizedSamples==again.synthesizedSamples,"P3 generator nondeterministic");
        for(size_t i=0;i<result.proposals.size();++i) {
            const auto& candidate=result.proposals[i];unchanged(base,candidate);
            need(packV9(candidate)!=original&&packV9(candidate)==packV9(again.proposals[i]),"P3 generator retained a no-op or changed tie ordering");
            int fields=0;
            for(int f=0;f<int(base.spectra.size());++f)for(int k=0;k<10;++k)if(candidate.spectra[f][k]!=base.spectra[f][k]) {
                const int distance=std::abs(candidate.spectra[f][k]-base.spectra[f][k]);
                need(distance==2||distance==4,"generator returned a raw distance outside2/4");++fields;
            }
            need(fields>0,"P3 generator returned no spectral edit");native(candidate);++proposals;
        }
        need(packV9(base)==original,"P3 generation mutated baseline");steps+=expected;++cases;
    }
    need(proposals>0,"P3 generator fixture exercised no returned proposal");
    std::printf("PASS generator: %d target/rate cases; %d exact legal spectral trials; %d legal native proposals\n",cases,steps,proposals);
    return 0;
}
int reachableTraces() {
    Checks checks;int continuationCases=0;
    for(int rate:{8000,12000,16000})for(int n:{1,41,161,321,641,1601}) {
        const auto base=neighborFixture(n,3,rate);const auto baseline=coefficientTrace(base);
        for(int frame=0;frame<int(base.spectra.size());++frame)for(int d:{-4,-2,2,4}) {
            const auto trial=edit(base,frame,frame+1,d);const auto pcm=native(trial);
            checks.noOps+=packV9(trial)==packV9(base);
            const auto canonical=canonicalAccuracy(trial);
            for(int f=0;f<int(base.spectra.size());++f)if(f!=frame&&canonical.spectra[f]!=base.spectra[f])++checks.propagated;
            for(int start:{0,320,640,1280})if(start<n)compare(trial,baseline,start,std::min(n,start+1280),pcm,checks);
        }
    }
    for(int rate:{8000,12000,16000})for(int tail:{1,321,1281}) {
        const int offset=1280;const auto whole=neighborFixture(offset+tail,3,rate);const auto prefix=native(whole);
        const auto chunk=suffix(whole,offset,prefix);const auto baseline=coefficientTrace(chunk);
        for(int frame=0;frame<int(chunk.spectra.size());++frame)for(int d:{-4,-2,2,4}) {
            const auto trial=edit(chunk,frame,frame+1,d);auto assembled=whole;
            std::copy(trial.spectra.begin(),trial.spectra.end(),assembled.spectra.begin()+offset/320);
            const auto full=native(assembled);const Pcm actual(full.begin()+offset,full.end());
            need(render(trial)==actual,"reachable P3 continuation differs from assembled native suffix");
            for(int start:{0,320,640})if(start<tail) {
                compare(trial,baseline,start,std::min(tail,start+1280),actual,checks);++continuationCases;
            }
        }
    }
    need(checks.noOps>0&&checks.propagated>0,"reachable traces did not exercise no-ops and dead-zone propagation");
    need(!checks.coefficientMismatches&&!checks.audioMismatches,"reachable P3 local trace differs from full canonical/native oracle");
    std::printf("PASS reachable traces: %d crops (%d real-prefix); %d canonical no-ops, %d later-frame propagation events\n",
        checks.cases,continuationCases,checks.noOps,checks.propagated);
    return 0;
}
int controlFingerprint() {
    need(traces(false)==0,"frozen non-P3 native crop controls failed");
    uint64_t hash=1469598103934665603ULL;int cases=0;
    auto add=[&](uint64_t value){for(int i=0;i<8;++i){hash^=uint8_t(value);hash*=1099511628211ULL;value>>=8;}};
    for(int level:{4,6,8})for(int rate:{8000,12000,16000}) {
        auto base=neighborFixture(641,level,rate);const Pcm reference(base.samples,32767);
        const auto result=proposeLpcRuns(base,reference,10000,true);
        add(result.runs);add(result.spectralEvaluations);add(result.pulseEvaluations);add(result.synthesizedSamples);add(result.proposals.size());
        for(const auto& proposal:result.proposals){unchanged(base,proposal);native(proposal);for(auto byte:packV9(proposal))add(byte);}
        auto a=edit(base,0,2,1),b=edit(base,2,3,-1);
        need(!composeLpcRuns(base,{a,b},{1.,2.},10000,true).empty(),"non-P3 magnitude1 composition changed");
        for(int distance:{-4,-2,2,4}) {
            auto wrong=edit(base,0,2,distance);
            need(composeLpcRuns(base,{wrong,b},{1.,2.},10000,true).empty(),"non-P3 composer accepted2/4 distance");
        }
        ++cases;
    }
    std::printf("PASS non-P3 fingerprint: %d generator/composer profile/rate cases; %016llx\n",cases,static_cast<unsigned long long>(hash));
    return 0;
}
}
int main(int argc,char** argv) {
    need(argc==2,"select composition, generator, reachable or controls");const std::string mode=argv[1];
    if(mode=="composition")return composeContracts();if(mode=="generator")return generatorContracts();
    if(mode=="reachable")return reachableTraces();if(mode=="controls")return controlFingerprint();return 2;
}
