// C++ adaptation of the non-extended algorithm in pystoi 0.4.1 (MIT).
// Copyright (c) 2018 Pariente Manuel. See LICENSE-pystoi.txt.
// Original: https://github.com/mpariente/pystoi/tree/v0.4.1
// Keep framing, FIR summation, silence mask and correlation order unchanged.
// Only frame energies scale with duration; filtered signals/OLA/STFT use rings.
#include "LpxQuality.h"
#include <algorithm>
#include <cmath>

namespace lpx {
static constexpr double pi=3.14159265358979323846,eps=2.2204460492503131e-16;
static const double filter[] = {
#include "stoi-resample.inc"
};
namespace {
using Bands=std::array<double,15>;
class ResampledFrames {
    const Pcm& pcm;
    int previous=-1000;
    double samples[256]={};
    double sample(int i) const {
        const int length=sizeof(filter)/sizeof(filter[0]),half=(length-1)/2;
        const int pre=4-half%4,remove=(half+pre)/4,at=(i+remove)*4-pre;
        int first=std::max(0,(at-length+5)/5),last=std::min(int(pcm.size())-1,at/5);
        double sum=0;
        for(int j=first;j<=last;++j) { int tap=at-j*5;if(tap>=0 && tap<length)sum+=pcm[j]/32768.0*filter[tap]; }
        return sum;
    }
public:
    explicit ResampledFrames(const Pcm& input):pcm(input) {}
    int size() const { return (pcm.size()*5+3)/4; }
    const double* at(int start) {
        int keep=start==previous+128?128:0;
        if(keep)for(int i=0;i<128;++i)samples[i]=samples[i+128];
        for(int i=keep;i<256;++i)samples[i]=sample(start+i);
        previous=start;return samples;
    }
};
class BandTransform {
    int low[15],high[15];
public:
    double window[256];
    BandTransform() {
        for(int i=0;i<256;++i)window[i]=.5-.5*std::cos(2*pi*(i+1)/257);
        for(int b=0;b<15;++b) {
            low[b]=int(std::floor(150*std::pow(2.,(2*b-1)/6.)*512/10000+.5));
            high[b]=int(std::floor(150*std::pow(2.,(2*b+1)/6.)*512/10000+.5));
        }
    }
    Bands bands(const double* previous,const double* current) const {
        double x[256],power[257];
        for(int i=0;i<128;++i) { x[i]=previous[i]*window[i];x[i+128]=current[i]*window[i+128]; }
        periodogram(x,256,power,512);Bands result;
        for(int b=0;b<15;++b) { double sum=0;for(int i=low[b];i<high[b];++i)sum+=power[i];result[b]=std::sqrt(sum); }
        return result;
    }
};
}
double stoi(const Pcm& reference,const Pcm& candidate) {
    double power=0;for(int x:reference)power+=double(x)*x;
    if(!power || reference.size()*10000ULL<=4096ULL*8000)return std::numeric_limits<double>::quiet_NaN();
    BandTransform transform;ResampledFrames firstPass(reference);
    std::vector<double> energies;double maximum=-1e300;
    for(int at=0;at+256<firstPass.size();at+=128) {
        const double* frame=firstPass.at(at);double energy=0;
        for(int i=0;i<256;++i) { double v=frame[i]*transform.window[i];energy+=v*v; }
        double db=20*std::log10(std::sqrt(energy)+eps);energies.push_back(db);maximum=std::max(maximum,db);
    }
    ResampledFrames x(reference),y(candidate);
    double tailX[128]={},tailY[128]={},previousX[128]={},previousY[128]={};
    Bands a[30],b[30];int accepted=0,frames=0;double correlations=0;
    for(int f=0;f<int(energies.size());++f)if(maximum-40-energies[f]<0) {
        const double* rawX=x.at(f*128);const double* rawY=y.at(f*128);
        double currentX[128],currentY[128];
        for(int i=0;i<128;++i) {
            currentX[i]=tailX[i]+rawX[i]*transform.window[i];
            currentY[i]=tailY[i]+rawY[i]*transform.window[i];
            tailX[i]=rawX[i+128]*transform.window[i+128];tailY[i]=rawY[i+128]*transform.window[i+128];
        }
        // Exclusive STFT framing yields accepted-1 frames. The last unpaired
        // 128-sample overlap-add tail is intentionally not transformed.
        if(accepted++) {
            a[frames%30]=transform.bands(previousX,currentX);b[frames%30]=transform.bands(previousY,currentY);++frames;
            if(frames>=30)for(int band=0;band<15;++band) {
                double xx=0,yy=0;
                for(int i=0;i<30;++i) { double va=a[(frames-30+i)%30][band],vb=b[(frames-30+i)%30][band];xx+=va*va;yy+=vb*vb; }
                double normalization=std::sqrt(xx)/(std::sqrt(yy)+eps),vx[30],vy[30],mx=0,my=0;
                for(int i=0;i<30;++i) { vx[i]=a[(frames-30+i)%30][band];vy[i]=std::min(b[(frames-30+i)%30][band]*normalization,vx[i]*(1+std::pow(10.,.75)));mx+=vx[i];my+=vy[i]; }
                mx/=30;my/=30;xx=yy=0;double xy=0;
                for(int i=0;i<30;++i) { vx[i]-=mx;vy[i]-=my;xx+=vx[i]*vx[i];yy+=vy[i]*vy[i];xy+=vx[i]*vy[i]; }
                correlations+=xy/((std::sqrt(xx)+eps)*(std::sqrt(yy)+eps));
            }
        }
        for(int i=0;i<128;++i) { previousX[i]=currentX[i];previousY[i]=currentY[i]; }
    }
    return frames<30?std::numeric_limits<double>::quiet_NaN():correlations/((frames-29)*15);
}
}
