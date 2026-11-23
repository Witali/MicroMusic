// C++ adaptation of the non-extended algorithm in pystoi 0.4.1 (MIT).
// Copyright (c) 2018 Pariente Manuel. See LICENSE-pystoi.txt.
// Original: https://github.com/mpariente/pystoi/tree/v0.4.1
// Resampling FIR is retained as constants, so neither Python nor SciPy is
// required by the encoder. EPS, exclusive framing and silence masks match it.
#include "LpxQuality.h"
#include <algorithm>
#include <cmath>

namespace lpx {
static constexpr double pi=3.14159265358979323846,eps=2.2204460492503131e-16;
static const double filter[] = {
#include "stoi-resample.inc"
};
static std::vector<double> resample(const Pcm& pcm) {
    const int length=sizeof(filter)/sizeof(filter[0]),half=(length-1)/2;
    const int pre=4-half%4,remove=(half+pre)/4;
    std::vector<double> out((pcm.size()*5+3)/4);
    for(int i=0;i<int(out.size());++i) {
        int at=(i+remove)*4-pre;
        // upfirdn sums taps in ascending input-sample order.
        int first=std::max(0,(at-length+5)/5),last=std::min(int(pcm.size())-1,at/5);
        double sum=0;for(int j=first;j<=last;++j) { int tap=at-j*5;if(tap>=0 && tap<length)sum+=pcm[j]/32768.0*filter[tap]; }
        out[i]=sum;
    }
    return out;
}
using Bands=std::array<double,15>;
static std::vector<Bands> stft(const std::vector<double>& samples) {
    int low[15],high[15];double window[256];
    for(int i=0;i<256;++i)window[i]=.5-.5*std::cos(2*pi*(i+1)/257);
    for(int b=0;b<15;++b) {
        low[b]=int(std::floor(150*std::pow(2.,(2*b-1)/6.)*512/10000+.5));
        high[b]=int(std::floor(150*std::pow(2.,(2*b+1)/6.)*512/10000+.5));
    }
    std::vector<Bands> frames;
    for(int at=0;at+256<int(samples.size());at+=128) {
        double x[256],power[257];for(int i=0;i<256;++i)x[i]=samples[at+i]*window[i];
        periodogram(x,256,power,512);Bands frame;
        for(int b=0;b<15;++b) { double sum=0;for(int i=low[b];i<high[b];++i)sum+=power[i];frame[b]=std::sqrt(sum); }
        frames.push_back(frame);
    }
    return frames;
}
double stoi(const Pcm& reference,const Pcm& candidate) {
    double power=0;for(int x:reference)power+=double(x)*x;
    if(!power || reference.size()*10000ULL<=4096ULL*8000)return std::numeric_limits<double>::quiet_NaN();
    auto x=resample(reference),y=resample(candidate);double window[256];
    for(int i=0;i<256;++i)window[i]=.5-.5*std::cos(2*pi*(i+1)/257);
    std::vector<double> energies;double maximum=-1e300;
    for(int at=0;at+256<int(x.size());at+=128) {
        double energy=0;for(int i=0;i<256;++i) { double v=x[at+i]*window[i];energy+=v*v; }
        double db=20*std::log10(std::sqrt(energy)+eps);energies.push_back(db);maximum=std::max(maximum,db);
    }
    std::vector<double> activeX,activeY;int accepted=0;
    for(int f=0;f<int(energies.size());++f)if(maximum-40-energies[f]<0) {
        activeX.resize(accepted*128+256,0);activeY.resize(accepted*128+256,0);
        for(int i=0;i<256;++i) { activeX[accepted*128+i]+=x[f*128+i]*window[i];activeY[accepted*128+i]+=y[f*128+i]*window[i]; }
        ++accepted;
    }
    auto a=stft(activeX),b=stft(activeY);
    if(a.size()<30)return std::numeric_limits<double>::quiet_NaN();
    double correlations=0;
    for(int first=0;first+30<=int(a.size());++first)for(int band=0;band<15;++band) {
        double xx=0,yy=0;
        for(int i=0;i<30;++i) { double va=a[first+i][band],vb=b[first+i][band];xx+=va*va;yy+=vb*vb; }
        double normalization=std::sqrt(xx)/(std::sqrt(yy)+eps),vx[30],vy[30],mx=0,my=0;
        for(int i=0;i<30;++i) { vx[i]=a[first+i][band];vy[i]=std::min(b[first+i][band]*normalization,vx[i]*(1+std::pow(10.,.75)));mx+=vx[i];my+=vy[i]; }
        mx/=30;my/=30;xx=yy=0;double xy=0;
        for(int i=0;i<30;++i) { vx[i]-=mx;vy[i]-=my;xx+=vx[i]*vx[i];yy+=vy[i]*vy[i];xy+=vx[i]*vy[i]; }
        correlations+=xy/((std::sqrt(xx)+eps)*(std::sqrt(yy)+eps));
    }
    return correlations/((a.size()-29)*15);
}
}
