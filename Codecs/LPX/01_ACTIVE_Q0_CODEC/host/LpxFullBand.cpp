#include "LpxFullBand.h"
#include "LpxQuality.h"
#include <algorithm>
#include <cmath>

namespace lpx {
static constexpr double pi=3.14159265358979323846;
int FullBandContext::band(int bin) const { return std::min(bands-1,bin*rate/(512*1000)); }
void FullBandContext::spectrum(const Pcm& samples,int start,double* power) const {
    double input[512];
    for(int i=0;i<512;++i) { int at=start+i;input[i]=at>=0 && at<int(samples.size())?samples[at]*window[i]:0.; }
    periodogram(input,512,power,512);
}
FullBandContext::FullBandContext(const Pcm& ref,int sampleRate,QualityTarget selectedTarget):target(selectedTarget),reference(ref),rate(sampleRate) {
    if(!validQualityTarget(target) || (rate!=8000 && rate!=12000 && rate!=16000) || ref.empty())return;
    bands=rate/2000;double windowPower=0;
    for(int i=0;i<512;++i) { window[i]=.5-.5*std::cos(2*pi*i/511);windowPower+=window[i]*window[i]; }
    for(int start=-256;start<int(ref.size());start+=256) {
        double power[257];spectrum(ref,start,power);++frames;
        for(int k=0;k<=256;++k)sourcePower[band(k)]+=power[k]*(k==0 || k==256?1:2);
    }
    normalization=frames*512*windowPower;
    for(int b=0;b<bands;++b)sourcePower[b]/=normalization;
}
FullBandMeasurement FullBandContext::measure(const Pcm& candidate) const {
    FullBandMeasurement m;m.target=target;
    if(target==QualityTarget::Pcm) {
        const double unavailable=std::numeric_limits<double>::quiet_NaN();
        m.totalError[1]=m.totalTemporalError[1]=m.balancedError[1]=m.balancedTemporalError[1]=unavailable;
        for(int b=0;b<8;++b)m.outputPower[1][b]=m.error[1][b]=m.retention[1][b]=m.temporalError[1][b]=unavailable;
    }
    if(!frames || candidate.size()!=reference.size())return m;
    m.valid=true;m.bands=bands;Pcm fixed;
    if(target==QualityTarget::Pwm)fixed=pwm(candidate);
    double totalSource=0;
    for(int b=0;b<bands;++b) { m.sourcePower[b]=sourcePower[b];totalSource+=sourcePower[b]; }
    for(int b=0;b<bands;++b)m.supported[b]=totalSource>0 && sourcePower[b]>1e-4*totalSource;
    double previousResidual[2][257]={};bool previous=false;
    for(int start=-256;start<int(reference.size());start+=256) {
        double source[257],native[257],quantized[257];
        spectrum(reference,start,source);spectrum(candidate,start,native);
        if(target==QualityTarget::Pwm)spectrum(fixed,start,quantized);
        for(int k=0;k<=256;++k)for(int path=0;path<qualityPathCount(target);++path) {
            int b=band(k);double actual=path?quantized[k]:native[k],weight=k==0 || k==256?1:2;
            double residual=std::sqrt(source[k])-std::sqrt(actual);
            m.outputPower[path][b]+=actual*weight;m.error[path][b]+=residual*residual*weight;
            if(previous) {
                double change=residual-previousResidual[path][k];
                m.temporalError[path][b]+=change*change*weight;
            }
            previousResidual[path][k]=residual;
        }
        previous=true;
    }
    for(int path=0;path<qualityPathCount(target);++path) {
        for(int b=0;b<bands;++b) {
            m.outputPower[path][b]/=normalization;m.error[path][b]/=normalization;
            m.temporalError[path][b]/=normalization;
            m.totalError[path]+=m.error[path][b];
            m.totalTemporalError[path]+=m.temporalError[path][b];
            const double floor=totalSource>0?std::max(sourcePower[b],totalSource*1e-4):1.;
            m.balancedError[path]+=m.error[path][b]/floor/bands;
            m.balancedTemporalError[path]+=m.temporalError[path][b]/floor/bands;
            m.retention[path][b]=sourcePower[b]>0?std::min(1.,std::sqrt(m.outputPower[path][b]/sourcePower[b])):0.;
            if(sourcePower[b]>0)m.error[path][b]/=sourcePower[b];
            if(sourcePower[b]>0)m.temporalError[path][b]/=sourcePower[b];
        }
        if(totalSource>0)m.totalError[path]/=totalSource;
        if(totalSource>0)m.totalTemporalError[path]/=totalSource;
    }
    return m;
}
bool FullBandContext::accepts(const FullBandMeasurement& next,const FullBandMeasurement& incumbent) const {
    if(!frames || !next.valid || !incumbent.valid || next.bands!=bands || incumbent.bands!=bands
        || next.target!=target || incumbent.target!=target || !validQualityTarget(target))return false;
    constexpr double tolerance=1e-12;
    for(int path=0;path<qualityPathCount(target);++path) {
        if(!std::isfinite(next.totalError[path]) || next.totalError[path]>incumbent.totalError[path]+tolerance)return false;
        for(int b=0;b<bands;++b)if(incumbent.supported[b]) {
            if(!std::isfinite(next.error[path][b]) || next.error[path][b]>incumbent.error[path][b]+tolerance)return false;
            if(!std::isfinite(next.retention[path][b]) || next.retention[path][b]+tolerance<incumbent.retention[path][b])return false;
        }
    }
    return true;
}
}
