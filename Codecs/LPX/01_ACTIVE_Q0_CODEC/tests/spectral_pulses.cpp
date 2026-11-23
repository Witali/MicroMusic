// Host proposal contracts. These proposals need the controller's full-output
// admission; a locally lower spectral error is deliberately not a quality gate.
#include "LpxSpectralPulses.h"
#include "LpxAdaptiveController.h"
#include <cstdio>

static lpx::Stream fixture(int n,int profile,int rate) {
    lpx::Stream s;s.samples=n;s.profile=profile;s.rate=rate;s.pre=0;
    const int frames=(n+319)/320;lpx::Spectrum spectrum;
    for(int j=0;j<10;++j)spectrum[j]=profile==4?1+3*j:3+5*j;
    s.spectra.assign(frames,spectrum);
    s.parameters.assign(frames*2,lpx::Parameters{{18,18,0}});
    s.pulses.assign(frames*16,lpx::Pulse{{0,-8}});
    s.extras.assign(frames*8,lpx::Pulse{{-1,0}});
    return s;
}
int main() {
    int cases=0,proposals=0;
    for(int profile:{4,6})for(int rate:{8000,12000,16000})
        for(int n:{1,19,20,21,39,40,41,319,320,321,1027,65537}) {
        auto input=fixture(n,profile,rate),target=input;
        target.pulses[0]=lpx::Pulse{{n>17?18:0,profile==4?8:7}};
        target.pulses[1]=lpx::Pulse{{9,profile==4?8:7}};
        const auto reference=lpx::render(target);const auto before=lpx::packV9(input);
        const int compact=lpx::compactBytes(input);
        const auto result=lpx::proposeSpectralPulses(input,reference);
        if(lpx::packV9(input)!=before)return 1;
        if(result.proposals.size()>3||result.regions>4||result.localEvaluations>4*8*301)return 2;
        for(const auto& proposal:result.proposals) {
            if(lpx::packV9(proposal).size()!=before.size()||lpx::compactBytes(proposal)!=compact)return 3;
            if(proposal.spectra!=input.spectra||proposal.parameters!=input.parameters||proposal.extras!=input.extras
                ||proposal.samples!=n||proposal.pre!=input.pre||proposal.bright!=input.bright
                ||proposal.rate!=rate||proposal.profile!=profile)return 4;
            for(size_t p=0;p<proposal.pulses.size();++p)if(proposal.pulses[p]!=input.pulses[p]) {
                const auto& pulse=proposal.pulses[p];
                if(pulse[0]<0||pulse[0]>=20||pulse[1]<-8||pulse[1]>(profile==4?8:7))return 5;
                if(profile==4&&(pulse[0]%5==2||(pulse[1]!=-8&&pulse[1]!=8)))return 6;
            }
            if(!lpx::verifyStream(proposal,lpx::render(proposal)))return 7;
            ++proposals;
        }
        if(n==1027) {
            const auto repeated=lpx::proposeSpectralPulses(input,reference);
            if(repeated.localEvaluations!=result.localEvaluations||repeated.proposals.size()!=result.proposals.size())return 8;
            for(size_t i=0;i<result.proposals.size();++i)
                if(lpx::packV9(repeated.proposals[i])!=lpx::packV9(result.proposals[i]))return 9;
        }
        ++cases;
    }
    auto invalid=fixture(41,4,8000);const auto reference=lpx::render(invalid);
    invalid.rate=11025;if(!lpx::proposeSpectralPulses(invalid,reference).proposals.empty())return 10;
    invalid.rate=8000;invalid.pulses.clear();if(!lpx::proposeSpectralPulses(invalid,reference).proposals.empty())return 11;
    if(!proposals)return 12;
    std::printf("PASS: %d spectral-pulse profile/rate/tail/Long cases; %d exact-width legal unguarded proposals.\n",cases,proposals);
}
