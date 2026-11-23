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
double integratedLoudness(const Pcm& pcm,int rate) {
    if(!validRate(rate) || pcm.size()<size_t(rate*4/10))return -std::numeric_limits<double>::infinity();
    const int hop=rate/10;KWeighting filter(rate);
    // Four 100-ms energy sums form each 400-ms block. Memory scales with the
    // number of gating blocks, not the number of filtered audio samples.
    double ring[4]={};int slot=0,used=0,within=0;double sum=0;
    std::vector<double> blocks;blocks.reserve(pcm.size()/hop);
    const double absolute=std::pow(10.,(-70.+0.691)/10);
    for(int16_t x:pcm) {
        double y=filter.next(x);sum+=y*y;
        if(++within!=hop)continue;
        ring[slot]=sum;slot=(slot+1)%4;sum=0;within=0;
        if(++used<4)continue;
        double energy=(ring[0]+ring[1]+ring[2]+ring[3])/(4*hop);
        if(energy>=absolute)blocks.push_back(energy);
    }
    if(blocks.empty())return -std::numeric_limits<double>::infinity();
    double total=0;for(double e:blocks)total+=e;
    double threshold=std::max(absolute,total/blocks.size()/10);
    total=0;size_t count=0;for(double e:blocks)if(e>=threshold) { total+=e;++count; }
    return count?asLufs(total/count):-std::numeric_limits<double>::infinity();
}
LoudnessReport normalizeLoudness(Pcm& pcm,int rate) {
    LoudnessReport report;
    if(!validRate(rate) || pcm.size()<size_t(rate*4/10)) { report.status=2;return report; }
    report.input=integratedLoudness(pcm,rate);report.prepared=report.input;
    if(!std::isfinite(report.input)) { report.status=3;return report; }
    int peak=0;for(int x:pcm)peak=std::max(peak,std::abs(x));
    const int ceiling=int(std::floor(32768*std::pow(10.,-1./20)));
    double wanted=std::pow(10.,(-18-report.input)/20),allowed=double(ceiling)/peak;
    double gain=std::min(wanted,allowed);report.status=1;report.limited=allowed<wanted;
    report.gainDb=20*std::log10(gain);
    for(auto& x:pcm)x=int16_t(std::max(-ceiling,std::min(ceiling,int(std::round(x*gain)))));
    report.prepared=integratedLoudness(pcm,rate);
    return report;
}
}
