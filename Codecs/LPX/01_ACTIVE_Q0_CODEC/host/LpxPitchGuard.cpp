#include "LpxPitchGuard.h"
#include "LpxQuality.h"
#include <cmath>

namespace lpx {
namespace {
uint8_t octaveMask(double source,double candidate) {
    if(!std::isfinite(source)||!std::isfinite(candidate))return 0;
    const double cents=1200*std::log2(source/candidate);
    return uint8_t((std::abs(cents+1200)<=100?1:0)|(std::abs(cents-1200)<=100?2:0));
}
double periodAt(const Pcm& pcm,std::size_t start,int count,int rate,std::vector<double>& scratch) {
    for(int i=0;i<count;++i)scratch[i]=pcm[start+i];
    double rms;return estimatePeriod(scratch.data(),count,rms,rate);
}
}
PitchGuardContext::PitchGuardContext(const Pcm& reference,const Pcm& incumbent,int sampleRate,QualityTarget selectedTarget):
    target(selectedTarget),rate(sampleRate),frame(0),hop(0),samples(reference.size()) {
    if(!validQualityTarget(target)||(rate!=8000&&rate!=12000&&rate!=16000)||!samples||incumbent.size()!=samples)return;
    frame=rate*80/1000;hop=rate*20/1000;
    std::vector<double> scratch(frame);Pcm fixed;
    if(target==QualityTarget::Pwm)fixed=pwm(incumbent);
    for(std::size_t start=0;start+frame<=samples;start+=hop) {
        const double source=periodAt(reference,start,frame,rate,scratch);sourcePeriods.push_back(source);
        baselineMasks[0].push_back(octaveMask(source,periodAt(incumbent,start,frame,rate,scratch)));
        if(target==QualityTarget::Pwm)baselineMasks[1].push_back(octaveMask(source,periodAt(fixed,start,frame,rate,scratch)));
    }
    valid=true;
}
bool PitchGuardContext::accepts(const Pcm& candidate) const {
    if(!valid||candidate.size()!=samples)return false;
    std::vector<double> scratch(frame);Pcm fixed;
    if(target==QualityTarget::Pwm)fixed=pwm(candidate);
    for(std::size_t index=0;index<sourcePeriods.size();++index) {
        const double source=sourcePeriods[index];if(!std::isfinite(source))continue;
        const std::size_t start=index*hop;
        for(int path=0;path<qualityPathCount(target);++path) {
            const double candidatePeriod=periodAt(path?fixed:candidate,start,frame,rate,scratch);
            if(octaveMask(source,candidatePeriod)&~baselineMasks[path][index])return false;
        }
    }
    return true;
}
}
