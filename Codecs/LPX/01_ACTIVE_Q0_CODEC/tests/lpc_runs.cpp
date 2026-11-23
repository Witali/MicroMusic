// Exercise the private coefficient-slice seam without exporting runtime APIs.
#include "LpxLpcRefine.cpp"
#include "LpxAdaptiveController.h"
#include <cstdio>
#include <limits>

static lpx::Stream fixture(int n,int profile,int rate) {
    lpx::Stream s;s.samples=n;s.profile=profile;s.rate=rate;s.pre=8192;s.bright=4096;
    const int frames=(n+319)/320;lpx::Spectrum a,b;
    for(int i=0;i<10;++i)a[i]=profile==4?1+3*i:3+5*i;b=a;++b[4];
    for(int f=0;f<frames;++f)s.spectra.push_back(f>=frames/3&&f<2*frames/3?b:a);
    s.parameters.assign(frames*2,lpx::Parameters{{18,95,10}});
    s.pulses.assign(frames*16,lpx::Pulse{{0,-8}});
    s.extras.assign(frames*8,lpx::Pulse{{-1,0}});s.extras[0]=lpx::Pulse{{7,2}};
    return s;
}
static lpx::Stream carriedFixture(int n,int profile,int rate,lpx::Stream* complete=nullptr) {
    const int cut=1280,future=n%1280==0?48:0,frames=(n+319)/320;
    auto whole=fixture(cut+n+future,profile,rate);auto a=whole.spectra[0],b=a;++b[4];
    for(int f=0;f<int(whole.spectra.size());++f)whole.spectra[f]=f<4?b:((f-4)/2)%2?b:a;
    whole.allowExtras=false;whole.extras.assign(whole.extras.size(),lpx::Pulse{{-1,0}});
    const auto co=lpx::coefficientTrace(whole);auto state=whole.initial;
    const auto prefix=lpx::advance(whole,co,0,cut,state);const auto all=lpx::render(whole);
    auto part=whole;part.samples=n;part.continuation=true;part.initial=state;part.previousSpectrum=whole.spectra[3];
    part.spectra.assign(whole.spectra.begin()+4,whole.spectra.begin()+4+frames);
    part.parameters.assign(whole.parameters.begin()+8,whole.parameters.begin()+8+frames*2);
    part.pulses.assign(whole.pulses.begin()+64,whole.pulses.begin()+64+frames*16);
    part.extras.assign(whole.extras.begin()+32,whole.extras.begin()+32+frames*8);
    std::copy(prefix.end()-172,prefix.end(),part.previousInput.begin());
    std::copy(co.begin()+56,co.begin()+64,part.previousCoefficients.begin());
    part.lookahead.assign(all.begin()+cut+n,all.end());
    if(complete)*complete=whole;
    return part;
}
static lpx::Stream joinedWith(const lpx::Stream& whole,const lpx::Stream& part) {
    auto joined=whole;
    std::copy(part.spectra.begin(),part.spectra.end(),joined.spectra.begin()+4);
    std::copy(part.parameters.begin(),part.parameters.end(),joined.parameters.begin()+8);
    std::copy(part.pulses.begin(),part.pulses.end(),joined.pulses.begin()+64);
    std::copy(part.extras.begin(),part.extras.end(),joined.extras.begin()+32);
    return joined;
}
static bool completeSuffix(const lpx::Stream& whole,const lpx::Stream& part) {
    const auto joined=joinedWith(whole,part);const auto co=lpx::coefficientTrace(joined);
    const auto expected=lpx::render(joined);const auto partCo=lpx::coefficientTrace(part);auto state=part.initial;
    const auto actual=lpx::advance(part,partCo,0,part.samples,state);
    if(!std::equal(actual.begin(),actual.end(),expected.begin()+1280))return false;
    const auto suffix=lpx::advance(joined,co,1280+part.samples,joined.samples,state);
    if(!std::equal(suffix.begin(),suffix.end(),expected.begin()+1280+part.samples))return false;
    return lpx::verifyStream(joined,expected);
}
static int compositionContracts(bool continued=false) {
    int cases=0;
    for(int profile:{4,6})for(int rate:{8000,12000,16000})for(bool finalBudget:{false,true}) {
        lpx::Stream whole;const auto anchor=continued?carriedFixture(2560,profile,rate,&whole):fixture(1920,profile,rate);
        const auto before=lpx::packV9(anchor);
        auto edit=[&](int first,int delta,bool pulse) {
            auto result=anchor;int last=first+1;while(last<int(anchor.spectra.size())&&anchor.spectra[last]==anchor.spectra[first])++last;
            for(int f=first;f<last;++f)result.spectra[f][5]+=delta;
            if(pulse)result.pulses[first*16]=lpx::Pulse{{5,profile==4?8:7}};
            return result;
        };
        std::vector<lpx::Stream> singles{edit(0,1,false),edit(0,-1,true),edit(2,1,true),edit(4,-1,true)};
        const std::vector<double> scores{.9,.8,.7,.75};
        const int cost=finalBudget?int(before.size()):lpx::compactBytes(anchor),cap=cost+64;
        const auto result=lpx::composeLpcRuns(anchor,singles,scores,cap,finalBudget);
        if(result.size()!=2||lpx::packV9(anchor)!=before)return -1;
        // All uses the best of the overlapping alternatives, never both.
        for(int f=0;f<2;++f)if(result[0].spectra[f]!=singles[1].spectra[f])return -2;
        if(result[0].pulses[0]!=singles[1].pulses[0])return -3;
        // Top-two uses runs at frames 2 and 4; run zero remains the anchor.
        if(result[1].spectra[0]!=anchor.spectra[0]||result[1].pulses[0]!=anchor.pulses[0])return -4;
        for(const auto& bundle:result) {
            if(bundle.parameters!=anchor.parameters||bundle.extras!=anchor.extras||bundle.pre!=anchor.pre
                ||bundle.bright!=anchor.bright||bundle.rate!=rate||bundle.profile!=profile||bundle.samples!=anchor.samples)return -5;
            if(!lpx::verifyStream(bundle,lpx::render(bundle)))return -6;
            if(!lpx::sameContinuation(bundle,anchor)||(continued&&!completeSuffix(whole,bundle)))return -18;
        }
        std::vector<double> ties{.8,.8,.7,.75};const auto tied=lpx::composeLpcRuns(anchor,singles,ties,cap,finalBudget);
        auto reversed=singles;std::reverse(reversed.begin(),reversed.end());std::reverse(ties.begin(),ties.end());
        const auto again=lpx::composeLpcRuns(anchor,reversed,ties,cap,finalBudget);
        if(tied.size()!=2||again.size()!=2)return -7;
        for(int i=0;i<2;++i)if(lpx::packV9(tied[i])!=lpx::packV9(again[i]))return -8;
        const auto a=lpx::packV9(singles[0]),b=lpx::packV9(singles[1]);
        const auto& preferred=a.size()<b.size()||(a.size()==b.size()&&a<b)?singles[0]:singles[1];
        if(tied[0].spectra[0]!=preferred.spectra[0]||tied[0].pulses[0]!=preferred.pulses[0])return -9;
        // Malformed alternatives must not reach serialization or rendering.
        auto malformed=singles;auto eligible=scores;
        auto bad=singles[0];bad.parameters.clear();malformed.push_back(bad);
        bad=singles[0];++bad.pre;malformed.push_back(bad);
        bad=anchor;++bad.spectra[1][5];malformed.push_back(bad);
        bad=singles[0];bad.pulses[8]=lpx::Pulse{{1,profile==4?8:7}};malformed.push_back(bad);
        eligible.resize(8,.1);const auto filtered=lpx::composeLpcRuns(anchor,malformed,eligible,cap,finalBudget);
        if(filtered.size()!=result.size())return -10;
        for(size_t i=0;i<result.size();++i)if(lpx::packV9(filtered[i])!=lpx::packV9(result[i]))return -11;
        for(int tight=cost;tight<=cap;++tight)for(const auto& bundle:lpx::composeLpcRuns(anchor,singles,scores,tight,finalBudget))
            if((finalBudget?int(lpx::packV9(bundle).size()):lpx::compactBytes(bundle))>tight)return -12;
        if(!lpx::composeLpcRuns(anchor,singles,scores,cost-1,finalBudget).empty())return -13;
        if(!lpx::composeLpcRuns(anchor,{}, {},cap,finalBudget).empty())return -14;
        if(!lpx::composeLpcRuns(anchor,{singles[0]},{.8},cap,finalBudget).empty())return -15;
        if(!lpx::composeLpcRuns(anchor,singles,std::vector<double>(4,std::numeric_limits<double>::infinity()),cap,finalBudget).empty())return -16;
        if(!lpx::composeLpcRuns(anchor,singles,{.8},cap,finalBudget).empty())return -17;
        for(int field=0;field<10;++field) {
            auto changed=singles[0];
            if(field==0)changed.continuation=!changed.continuation;
            if(field==1)changed.allowExtras=!changed.allowExtras;
            if(field==2)++changed.initial.h[0];
            if(field==3)++changed.initial.ring[255];
            if(field==4)++changed.previousSpectrum[0];
            if(field==5)++changed.previousInput[0];
            if(field==6)++changed.previousCoefficients[0][0];
            if(field==7)changed.lookahead.push_back(1);
            if(field==8)++changed.initial.dd;
            if(field==9)++changed.initial.cc;
            const auto rejected=lpx::composeLpcRuns(anchor,{changed,singles[2]},{.1,.2},cap,finalBudget);
            if(!rejected.empty())return -19;
        }
        ++cases;
    }
    return cases;
}
static int continuationContracts() {
    int cases=0;
    for(int profile:{4,6})for(int rate:{8000,12000,16000})for(int n:{1,41,321,1280,65537}) {
        lpx::Stream whole;auto input=carriedFixture(n,profile,rate,&whole),target=input;
        int last=1;while(last<int(input.spectra.size())&&input.spectra[last]==input.spectra[0])++last;
        for(int f=0;f<last;++f)++target.spectra[f][5];
        const auto targetPcm=lpx::render(joinedWith(whole,target));
        std::copy(targetPcm.begin()+1280-172,targetPcm.begin()+1280,input.previousInput.begin());
        input.lookahead.assign(targetPcm.begin()+1280+n,targetPcm.end());target.previousInput=input.previousInput;target.lookahead=input.lookahead;
        const lpx::Pcm reference(targetPcm.begin()+1280,targetPcm.begin()+1280+n);
        const auto originalCo=lpx::coefficientTrace(input),full=lpx::coefficientTrace(target);auto local=originalCo;
        const int end=std::min(n,1280);lpx::localCoefficients(target,0,end,local);
        for(int p=0;p<(end+19)/20;++p)if(local[p]!=full[p])return -1;
        auto state=input.initial;const auto actual=lpx::advance(target,local,0,end,state);
        if(!std::equal(actual.begin(),actual.end(),reference.begin())||!completeSuffix(whole,target))return -2;
        for(bool finalBudget:{false,true}) {
            const int cap=(finalBudget?int(lpx::packV9(input).size()):lpx::compactBytes(input))+8;
            const auto result=lpx::proposeLpcRuns(input,reference,cap,finalBudget);
            for(const auto& proposal:result.proposals) {
                if(!lpx::sameContinuation(proposal,input)||proposal.extras!=input.extras||proposal.allowExtras)return -3;
                if(!completeSuffix(whole,proposal))return -4;
            }
            ++cases;
        }
    }
    return cases;
}
int main() {
    int cases=0,proposals=0,slices=0;
    for(int profile:{4,6})for(int rate:{8000,12000,16000})
        for(int n:{1,19,20,21,39,40,41,319,320,321,1027,65537}) {
        const auto input=fixture(n,profile,rate);auto target=input;
        const auto originalBytes=lpx::packV9(input);
        int last=1;while(last<int(input.spectra.size())&&input.spectra[last]==input.spectra[0])++last;
        for(int f=0;f<last;++f)++target.spectra[f][5];
        const auto reference=lpx::render(target);
        const auto originalCo=lpx::coefficientTrace(input);
        for(int frame=0;frame<int(input.spectra.size());++frame)if(!frame||input.spectra[frame]!=input.spectra[frame-1]) {
            auto changed=input;int endFrame=frame+1;while(endFrame<int(input.spectra.size())&&input.spectra[endFrame]==input.spectra[frame])++endFrame;
            for(int f=frame;f<endFrame;++f)++changed.spectra[f][5];
            auto local=originalCo;const auto full=lpx::coefficientTrace(changed);
            const int start=frame*320,end=std::min(n,start+1280);
            lpx::localCoefficients(changed,start,end,local);
            for(int i=start/20;i<(end+19)/20;++i)if(local[i]!=full[i])return 1;
            lpx::SynthesisState prefix;lpx::advance(input,originalCo,0,start,prefix);
            const auto actual=lpx::advance(changed,local,start,end,prefix),complete=lpx::render(changed);
            if(!std::equal(actual.begin(),actual.end(),complete.begin()+start))return 2;
            ++slices;
        }
        for(bool finalBudget:{false,true}) {
            const int originalCost=finalBudget?int(originalBytes.size()):lpx::compactBytes(input),cap=originalCost+8;
            const auto result=lpx::proposeLpcRuns(input,reference,cap,finalBudget);
            if(lpx::packV9(input)!=originalBytes)return 3;
            if(result.runs>4||result.proposals.size()>8||result.spectralEvaluations>80
                ||result.pulseEvaluations>1536||result.synthesizedSamples>2080000)return 4;
            for(const auto& candidate:result.proposals) {
                if((finalBudget?int(lpx::packV9(candidate).size()):lpx::compactBytes(candidate))>cap)return 5;
                if(candidate.parameters!=input.parameters||candidate.extras!=input.extras||candidate.pre!=input.pre
                    ||candidate.bright!=input.bright||candidate.profile!=profile||candidate.rate!=rate||candidate.samples!=n)return 6;
                int changedRuns=0;
                for(int first=0;first<int(input.spectra.size());) {
                    int last=first+1;while(last<int(input.spectra.size())&&input.spectra[last]==input.spectra[first])++last;
                    if(candidate.spectra[first]!=input.spectra[first]) {
                        ++changedRuns;int differences=0;
                        for(int k=0;k<10;++k)if(candidate.spectra[first][k]!=input.spectra[first][k]) {
                            ++differences;if(std::abs(candidate.spectra[first][k]-input.spectra[first][k])!=1)return 7;
                        }
                        if(differences!=1)return 8;
                        for(int f=first;f<last;++f)if(candidate.spectra[f]!=candidate.spectra[first])return 9;
                    } else for(int f=first;f<last;++f)if(candidate.spectra[f]!=input.spectra[f])return 10;
                    first=last;
                }
                if(changedRuns!=1)return 11;
                for(const auto& spectrum:candidate.spectra)if(!lpx::legalSpectrum(spectrum,profile))return 12;
                if(!lpx::verifyStream(candidate,lpx::render(candidate)))return 13;
                ++proposals;
            }
            const auto noFit=lpx::proposeLpcRuns(input,reference,originalCost-1,finalBudget);
            if(!noFit.proposals.empty()||noFit.spectralEvaluations||noFit.pulseEvaluations)return 14;
            ++cases;
        }
    }
    if(!proposals)return 15;
    const int composed=compositionContracts();if(composed!=12)return 20-composed;
    const int carriedComposed=compositionContracts(true);if(carriedComposed!=12)return 50-carriedComposed;
    const int continued=continuationContracts();if(continued!=60)return 80-continued;
    std::printf("PASS: %d default LPC cases, %d coefficient/prefix slices, %d proposals, %d default/%d continued composition matrices, %d carried-state cases.\n",cases,slices,proposals,composed,carriedComposed,continued);
    return 0;
}
