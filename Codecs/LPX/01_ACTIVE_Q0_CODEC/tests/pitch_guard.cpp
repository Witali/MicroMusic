#include "LpxPitchGuard.h"
#include "LpxQuality.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>

// Frozen ba02e453 estimator: numerical characterization of the legacy entry
// point, retained independently of the new generic-rate scratch kernel.
static double frozen8k(const double* input,int count,double& rms) {
    const double nan=std::numeric_limits<double>::quiet_NaN();
    double x[640],mean=0,maximum=0,energy=0;
    for(int i=0;i<count;++i)mean+=input[i];mean/=count;
    for(int i=0;i<count;++i) {x[i]=input[i]-mean;energy+=x[i]*x[i];maximum=std::max(maximum,std::abs(x[i]));}
    rms=std::sqrt(energy/count);if(rms<.5)return nan;
    for(int i=0;i<count;++i)x[i]/=maximum;
    double difference[162]={},cmnd[162]={1},denominator=0;
    for(int lag=1;lag<=161;++lag) {
        for(int i=0;i<count-161;++i) {double d=x[i]-x[i+lag];difference[lag]+=d*d;}
        denominator+=difference[lag];cmnd[lag]=denominator>std::numeric_limits<double>::min()?difference[lag]*lag/denominator:1;
    }
    for(int lag=10;lag<=160;++lag)if(cmnd[lag]<=cmnd[lag-1]&&cmnd[lag]<cmnd[lag+1]&&cmnd[lag]<.15) {
        double left=difference[lag-1],middle=difference[lag],right=difference[lag+1];double curvature=left-2*middle+right;
        double offset=curvature>0?(left-right)/(2*curvature):0;
        double period=lag+std::max(-.5,std::min(.5,offset));double hz=8000/period;
        return hz>=50&&hz<=800?period:nan;
    }
    return nan;
}
static lpx::Pcm tone(int rate,int hz,int samples,int amplitude) {
    lpx::Pcm pcm(samples);const int period=rate/hz;
    for(int i=0;i<samples;++i)pcm[i]=i%period<period/2?amplitude:-amplitude;
    return pcm;
}
static double period(const lpx::Pcm& pcm,int start,int rate) {
    std::vector<double> frame(rate*80/1000);for(int i=0;i<int(frame.size());++i)frame[i]=pcm[start+i];
    double rms;return lpx::estimatePeriod(frame.data(),frame.size(),rms,rate);
}
static int halfCount(const lpx::Pcm& reference,const lpx::Pcm& pcm,int rate) {
    int count=0;const int frame=rate*80/1000,hop=rate*20/1000;
    for(int at=0;at+frame<=int(pcm.size());at+=hop) {
        const double a=period(reference,at,rate),b=period(pcm,at,rate);
        count+=std::isfinite(a)&&std::isfinite(b)&&std::abs(1200*std::log2(a/b)+1200)<=100;
    }
    return count;
}
extern "C" int lpx_pitch_guard_selftest() {
    int cases=0;
    for(int rate:{8000,12000,16000}) {
        const int n=rate/2,frame=rate*80/1000;
        const auto reference=tone(rate,200,n,4000),half=tone(rate,100,n,4000),twice=tone(rate,400,n,4000);
        const lpx::Pcm silence(n);lpx::PitchGuardContext correct(reference,reference,rate);
        if(!correct.accepts(reference)||correct.accepts(half)||correct.accepts(twice)||!correct.accepts(silence))return -1;
        lpx::PitchGuardContext oldHalf(reference,half,rate);
        if(!oldHalf.accepts(half)||!oldHalf.accepts(reference)||!oldHalf.accepts(silence)||oldHalf.accepts(twice))return -2;
        lpx::PitchGuardContext oldMissing(reference,silence,rate);
        if(oldMissing.accepts(half)||oldMissing.accepts(twice)||!oldMissing.accepts(reference))return -3;
        lpx::PitchGuardContext noSource(silence,silence,rate);if(!noSource.accepts(half))return -4;
        const auto quiet=tone(rate,200,n,1),quietHalf=tone(rate,100,n,1);
        lpx::PitchGuardContext quietGuard(quiet,quiet,rate);
        if(!quietGuard.accepts(quiet)||quietGuard.accepts(quietHalf))return -5;
        // PCM keeps the correct period, while thresholded PWM has only every
        // second cycle. A PCM-only guard would miss this new octave label.
        const auto pwmReference=tone(rate,200,n,128);auto pwmHalf=pwmReference;
        const int cycle=rate/200;
        for(int i=0;i<n;++i)pwmHalf[i]=(i/cycle)%2?pwmReference[i]:(pwmReference[i]>0?120:-120);
        if(std::abs(1200*std::log2(period(pwmReference,0,rate)/period(pwmHalf,0,rate)))>100)return -6;
        if(std::abs(1200*std::log2(period(pwmReference,0,rate)/period(lpx::pwm(pwmHalf),0,rate))+1200)>100)return -7;
        lpx::PitchGuardContext pwmGuard(pwmReference,pwmReference,rate);if(pwmGuard.accepts(pwmHalf))return -8;
        // Move an equal number of half-pitch windows to a disjoint source
        // region: a count ceiling passes, but per-window membership must fail.
        lpx::Pcm splitSource(frame*10),before(frame*10),after(frame*10);
        const auto refAll=tone(rate,200,frame*10,4000),halfAll=tone(rate,100,frame*10,4000);
        for(int i=frame*2;i<frame*4;++i) {splitSource[i]=refAll[i];before[i]=halfAll[i];after[i]=refAll[i];}
        for(int i=frame*6;i<frame*8;++i) {splitSource[i]=refAll[i];before[i]=refAll[i];after[i]=halfAll[i];}
        const int oldCount=halfCount(splitSource,before,rate),newCount=halfCount(splitSource,after,rate);
        if(!oldCount||oldCount!=newCount)return -9;
        lpx::PitchGuardContext swapped(splitSource,before,rate);if(swapped.accepts(after)||!swapped.accepts(splitSource))return -10;
        if(correct.accepts(lpx::Pcm(n-1)))return -11;
        lpx::PitchGuardContext invalid(reference,reference,11025);if(invalid.accepts(reference))return -12;
        ++cases;
    }
    uint32_t state=0x91abcdef;
    for(int pattern=0;pattern<32;++pattern)for(int count:{1,160,320,640}) {
        double input[640];for(int i=0;i<count;++i) {
            state^=state<<13;state^=state>>17;state^=state<<5;
            input[i]=pattern%4==0?0:pattern%4==1?(i%40<20?4000:-4000):pattern%4==2?int(state%65536)-32768:(int(state%21)-10)*.01;
        }
        double aRms,bRms;const double a=frozen8k(input,count,aRms),b=lpx::estimatePeriod(input,count,bRms);
        if(std::memcmp(&a,&b,8)||std::memcmp(&aRms,&bRms,8))return -13;
        if(count>161) {double cRms;const double c=lpx::estimatePeriod(input,count,cRms,8000);if(std::memcmp(&a,&c,8)||std::memcmp(&aRms,&cRms,8))return -14;}
        ++cases;
    }
    return cases;
}
static lpx::Pcm readPcm(const char* path) {
    std::FILE* file=std::fopen(path,"rb");if(!file)return {};
    std::fseek(file,0,SEEK_END);const long bytes=std::ftell(file);std::rewind(file);
    lpx::Pcm pcm(bytes/2);const bool valid=bytes>0&&!(bytes%2)&&std::fread(pcm.data(),2,pcm.size(),file)==pcm.size();
    std::fclose(file);return valid?pcm:lpx::Pcm{};
}
int main(int argc,char** argv) {
    const int cases=lpx_pitch_guard_selftest();if(cases!=131) {std::printf("FAIL %d\n",cases);return 1;}
    if(argc==4) {
        const auto source=readPcm(argv[1]),baseline=readPcm(argv[2]),candidate=readPcm(argv[3]);
        if(source.empty()||source.size()!=baseline.size()||candidate.size()!=source.size())return 2;
        lpx::PitchGuardContext guard(source,baseline,8000);
        if(!guard.accepts(baseline)||guard.accepts(candidate))return 3;
    } else if(argc!=1)return 4;
    std::printf("PASS: %d actual-rate octave/PWM/quiet/window-swap/frozen-8k contracts%s.\n",cases,argc==4?" and public ambiguous-to-half rejection":"");
}
