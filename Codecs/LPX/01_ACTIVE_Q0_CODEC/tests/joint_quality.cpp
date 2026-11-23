// Full-output contracts for the appended phase, independently of its proposals.
#include "LpxProfileQuality.h"
#include "LpxAdaptiveController.h"
#include "LpxBitrateProfiles.h"
#include "LpxEncoder.h"
#include "LpxFullBand.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>

namespace {
int checks=0,improvements=0;
void require(bool value,const char* message) {
    if(!value) {std::fprintf(stderr,"FAIL: %s\n",message);std::exit(1);}
}
lpx::Pcm signal(int count,int rate,bool wide=true) {
    lpx::Pcm pcm(count);unsigned noise=19;
    for(int i=0;i<count;++i) {
        noise=noise*1664525u+1013904223u;
        double t=double(i)/rate;
        pcm[i]=int16_t(std::nearbyint(6000*std::sin(6.283185307179586*223*t)
            +1700*std::sin(6.283185307179586*(wide?.43*rate:1533)*t)+int(noise>>24)-128));
    }
    return pcm;
}
void check(const lpx::Stream& input,const lpx::Pcm& reference,int cap,bool final,bool threeK=false,bool speech=true) {
    const auto frozen=lpx::packV9(input);
    const auto beforePcm=lpx::render(input);
    lpx::QualityContext context(reference,speech,input.rate);
    lpx::FullBandContext spectrum(reference,input.rate);
    const auto before=context.measure(beforePcm);
    const auto bands=spectrum.measure(beforePcm);
    lpx::JointQualityReport report;
    const auto selected=lpx::refineJointQuality(input,reference,cap,final,report,threeK,speech);
    require(!report.selection.error&&selected.samples==input.samples,"valid joint search failed");
    require(lpx::packV9(input)==frozen,"joint search mutated incumbent");
    require(selected.rate==input.rate&&selected.profile==input.profile,"joint search changed format");
    require((final?int(lpx::packV9(selected).size()):lpx::compactBytes(selected))<=cap,"joint cap exceeded");
    const auto pcm=lpx::render(selected);
    require(lpx::verifyStream(selected,pcm),"complete C decoder mismatch");
    const auto after=context.measure(pcm);
    const auto nextBands=spectrum.measure(pcm);
    require(after.clipped<=before.clipped,"PCM clipping floor failed");
    for(int path=0;path<2;++path) {
        require(after.diagnostic[path].within>=before.diagnostic[path].within
            &&after.diagnostic[path].collapsed<=before.diagnostic[path].collapsed,"voice count floor failed");
        require(!std::isfinite(before.quality.stoi[path])||(std::isfinite(after.quality.stoi[path])
            &&after.quality.stoi[path]>=before.quality.stoi[path]-1e-12),"STOI floor failed");
        require(nextBands.totalError[path]<=bands.totalError[path]+1e-12
            &&nextBands.balancedError[path]<=bands.balancedError[path]+1e-12
            &&nextBands.balancedTemporalError[path]<=bands.balancedTemporalError[path]+1e-12,"spectral/time floor failed");
    }
    require(std::isfinite(report.selection.finalObjective)
        &&report.selection.finalObjective<=report.selection.initialObjective+1e-12,"joint objective regressed");
    require(report.headerLocalEvaluations<=(threeK?512:0)
        &&report.headerFullEvaluations<=(threeK?32:0)
        &&report.lpcRuns<=4&&report.lpcProposals<=8&&report.lpcBundles<=2,"bounded work exceeded");
    if(report.selection.finalObjective<report.selection.initialObjective-1e-12)++improvements;
    ++checks;
}
}
int main() {
    require(enc_reserve(128001),"workspace allocation failed");
    for(int rate:{8000,12000,16000})for(int profile:{4,6}) {
        auto reference=signal(1601,rate);
        const auto seed=lpx::fitSeed(reference,profile,rate,13926,true);
        check(seed,reference,lpx::compactBytes(seed),false);
        check(seed,reference,lpx::packV9(seed).size(),true);
    }
    int strictChecks=0;
    for(int samples:{3201,6401}) {
        auto reference=signal(samples,8000,false);lpx::BitrateReport generated;
        const int cap=samples*3/64;
        const auto initial=lpx::encodeThreeK(reference,cap,generated);
        require(!generated.error,"active strict3k fixture must fit");
        check(initial,reference,cap,true,true);++strictChecks;
    }
    lpx::Pcm silence(128001);
    const auto zero=lpx::fitSeed(silence,4,8000,13926,true);
    check(zero,silence,lpx::packV9(zero).size(),true,true);
    // A deliberately damaged spectrum has a legal, exact repair in the
    // existing alphabet; admission must be able to choose a genuine gain.
    auto reference=signal(1600,8000);auto target=lpx::fitSeed(reference,4,8000,13926,true);
    auto damaged=target;bool changed=false;
    for(int field=0;field<10&&!changed;++field)if(damaged.spectra[1][field]+1<(field==9?32:damaged.spectra[1][field+1])) {
        ++damaged.spectra[1][field];changed=true;
    }
    require(changed,"constructed damage unavailable");
    reference=lpx::render(target);
    const int cap=std::max(lpx::compactBytes(target),lpx::compactBytes(damaged));
    check(damaged,reference,cap,false);
    lpx::JointQualityReport report;
    const auto bad=lpx::refineJointQuality(target,reference,-1,true,report);
    require(!bad.samples&&report.selection.error==-6,"invalid cap accepted");
    auto invalid=target;invalid.rate=22050;
    require(!lpx::refineJointQuality(invalid,reference,cap,false,report).samples
        &&report.selection.error==-1,"unsupported rate accepted");
    require(improvements>0,"no constructed or synthetic improvement was admitted");
    require(strictChecks==2,"active strict3k contracts were skipped");
    std::printf("{\"checks\":%d,\"improvements\":%d,\"complete_gates_passed\":true}\n",checks,improvements);
}
