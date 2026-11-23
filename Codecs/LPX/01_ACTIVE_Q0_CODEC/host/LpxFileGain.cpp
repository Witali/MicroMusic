#include "LpxLoudness.h"
#include "Lpx4HybridCore.h"
#include "Lpx4FileGain.h"
#include "LpxHostWorkspace.h"
#include <algorithm>
#include <cmath>

namespace lpx {
static bool decodeFile(const std::vector<uint8_t>& bytes,Pcm& pcm,int& rate) {
    Lpx4HybridCore core;if(!core.beginWideV9(bytes.data(),bytes.size()) || core.samples()>kLpxMaxSamples)return false;
    pcm.resize(core.samples());rate=core.sampleRate();
    for(auto& x:pcm)if(!core.nextS16(x))return false;
    int16_t tail;return !core.nextS16(tail) && !core.error() && core.finished();
}
bool normalizeFileGain(std::vector<uint8_t>& bytes,int targetLufs,int maxGainDb,LoudnessReport& report) {
    report=LoudnessReport{};
    if(targetLufs<-30 || targetLufs>-9 || maxGainDb<0 || maxGainDb>24 || bytes.size()<13 || bytes.size()>kLpxMaxFileBytes
       || bytes[0]!='L' || bytes[1]!='9')return false;
    const size_t header=(bytes[2]&64)?17:13;
    if(bytes.size()<header+((bytes[2]&32)?2:0))return false;
    if((bytes[2]&32) && !(bytes[header] || bytes[header+1]))return false;
    auto plain=bytes;
    if(plain[2]&32) { plain.erase(plain.begin()+header,plain.begin()+header+2);plain[2]&=~32; }
    Pcm raw;int rate;if(!decodeFile(plain,raw,rate))return false;
    report.input=integratedLoudness(raw,rate);report.prepared=report.input;
    if(raw.size()<size_t(rate*4/10))report.status=2;
    else if(!std::isfinite(report.input))report.status=3;
    else {
        int peak=0;for(int x:raw)peak=std::max(peak,x==32767?32768:std::abs(x));
        const double wanted=std::pow(10.,(targetLufs-report.input)/20);
        const double maximum=std::pow(10.,maxGainDb/20.);
        const int ceiling=int(std::floor(32768*std::pow(10.,-1./20)));
        const double peakLimit=double(ceiling)/peak;
        const double selected=std::min(wanted,std::min(maximum,peakLimit));
        report.gainQ12=uint16_t(std::max(1,std::min(65535,int(std::floor(selected*4096)))));
        report.gainDb=20*std::log10(double(report.gainQ12)/4096);
        report.status=1;report.limited=peakLimit<wanted && peakLimit<=maximum;
        report.gainLimited=maximum<wanted && maximum<=peakLimit;
    }
    Pcm expected=raw;
    if(report.gainQ12!=4096)for(auto& x:expected)x=lpx4FileGainPcm16(x,report.gainQ12);
    report.decoded=integratedLoudness(expected,rate);
    plain[2]|=32;plain.insert(plain.begin()+header,{uint8_t(report.gainQ12),uint8_t(report.gainQ12>>8)});
    Pcm actual;int actualRate;
    if(!decodeFile(plain,actual,actualRate) || actualRate!=rate || actual!=expected)return false;
    bytes.swap(plain);return true;
}
}
