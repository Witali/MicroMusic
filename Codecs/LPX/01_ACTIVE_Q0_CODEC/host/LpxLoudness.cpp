// Mono BS.1770 measurement and project-specific constant-gain normalization.
// Filter design adapted from libebur128 v1.2.6 (Jan Kokemuller, MIT).
// See LICENSE-libebur128.txt and LOUDNESS.md for provenance and constraints.
#include "LpxLoudness.h"
#include <algorithm>
#include <cmath>

namespace lpx {
namespace {
struct KWeighting {
    double a[5]={},b[5]={},v[5]={};
    explicit KWeighting(int rate) {
        const double pi=3.14159265358979323846;
        double k=std::tan(pi*1681.974450955533/rate),q=0.7071752369554196;
        const double vh=std::pow(10.,3.999843853973347/20),vb=std::pow(vh,0.4996667741545416);
        double d=1+k/q+k*k;
        double p[3]={(vh+vb*k/q+k*k)/d,2*(k*k-vh)/d,(vh-vb*k/q+k*k)/d};
        double s[3]={1,2*(k*k-1)/d,(1-k/q+k*k)/d};
        k=std::tan(pi*38.13547087602444/rate);q=0.5003270373238773;d=1+k/q+k*k;
        double r[3]={1,-2,1},t[3]={1,2*(k*k-1)/d,(1-k/q+k*k)/d};
        for(int i=0;i<3;++i)for(int j=0;j<3;++j) { b[i+j]+=p[i]*r[j];a[i+j]+=s[i]*t[j]; }
    }
    double next(int16_t sample) {
        v[0]=double(sample)/32768;
        for(int i=1;i<5;++i)v[0]-=a[i]*v[i];
        double out=b[0]*v[0];for(int i=1;i<5;++i)out+=b[i]*v[i];
        for(int i=4;i>0;--i)v[i]=v[i-1];
        return out;
    }
};
bool validRate(int rate) { return rate==8000 || rate==12000 || rate==16000; }
double asLufs(double energy) { return energy>0?-0.691+10*std::log10(energy):-std::numeric_limits<double>::infinity(); }
}
struct LoudnessMeter::Impl {
    int rate,hop,slot=0,used=0,within=0,peak=0;
    uint64_t samples=0;
    KWeighting filter;
    double ring[4]={},sum=0;
    std::vector<double> blocks;
    explicit Impl(int sampleRate):rate(sampleRate),hop(sampleRate/10),filter(validRate(sampleRate)?sampleRate:8000) {}
};
LoudnessMeter::LoudnessMeter(int rate):state(new Impl(rate)) {}
LoudnessMeter::~LoudnessMeter()=default;
void LoudnessMeter::add(const int16_t* pcm,size_t count) {
    auto& s=*state;if(!validRate(s.rate))return;
    const double absolute=std::pow(10.,(-70.+0.691)/10);
    for(size_t i=0;i<count;++i) {
        int x=pcm[i];++s.samples;s.peak=std::max(s.peak,std::abs(x));
        double y=s.filter.next(x);s.sum+=y*y;
        if(++s.within!=s.hop)continue;
        s.ring[s.slot]=s.sum;s.slot=(s.slot+1)%4;s.sum=0;s.within=0;
        if(++s.used<4)continue;
        double energy=(s.ring[0]+s.ring[1]+s.ring[2]+s.ring[3])/(4*s.hop);
        if(energy>=absolute)s.blocks.push_back(energy);
    }
}
double LoudnessMeter::measure() const {
    const auto& s=*state;
    if(!validRate(s.rate) || s.samples<uint64_t(s.rate*4/10) || s.blocks.empty())return -std::numeric_limits<double>::infinity();
    const double absolute=std::pow(10.,(-70.+0.691)/10);
    double total=0;for(double e:s.blocks)total+=e;
    double threshold=std::max(absolute,total/s.blocks.size()/10);
    total=0;size_t count=0;for(double e:s.blocks)if(e>=threshold) { total+=e;++count; }
    return count?asLufs(total/count):-std::numeric_limits<double>::infinity();
}
LoudnessReport LoudnessMeter::plan(int target,int maxGain) const {
    LoudnessReport report;const auto& s=*state;
    if(target<-30 || target>-9 || maxGain<-1 || maxGain>24) { report.status=-1;return report; }
    if(!validRate(s.rate) || s.samples<uint64_t(s.rate*4/10)) { report.status=2;return report; }
    report.input=measure();report.prepared=report.input;
    if(!std::isfinite(report.input)) { report.status=3;return report; }
    const int ceiling=int(std::floor(32768*std::pow(10.,-1./20)));
    double wanted=std::pow(10.,(target-report.input)/20),allowed=double(ceiling)/s.peak;
    double maximum=maxGain<0?std::numeric_limits<double>::infinity():std::pow(10.,maxGain/20.);
    report.factor=std::min(wanted,std::min(allowed,maximum));report.status=1;
    report.limited=allowed<wanted && allowed<=maximum;
    report.gainLimited=maximum<wanted && maximum<=allowed;
    report.gainDb=20*std::log10(report.factor);return report;
}
double integratedLoudness(const Pcm& pcm,int rate) {
    LoudnessMeter meter(rate);meter.add(pcm.data(),pcm.size());return meter.measure();
}
static LoudnessReport applyLoudness(Pcm& pcm,int rate,int target,int maxGain) {
    LoudnessMeter meter(rate);meter.add(pcm.data(),pcm.size());auto report=meter.plan(target,maxGain);
    if(report.status!=1)return report;
    const int ceiling=int(std::floor(32768*std::pow(10.,-1./20)));
    for(auto& x:pcm)x=int16_t(std::max(-ceiling,std::min(ceiling,int(std::round(x*report.factor)))));
    report.prepared=integratedLoudness(pcm,rate);return report;
}
LoudnessReport normalizeLoudness(Pcm& pcm,int rate) { return applyLoudness(pcm,rate,-18,-1); }
LoudnessReport normalizeLoudness(Pcm& pcm,int rate,int target,int maxGain) {
    if(target<-30 || target>-9 || maxGain<0 || maxGain>24) { LoudnessReport report;report.status=-1;return report; }
    return applyLoudness(pcm,rate,target,maxGain);
}
}
