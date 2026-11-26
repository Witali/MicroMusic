// C++ translation of speech_voice_objective.py, speech_noise_objective.py,
// voice_character.py and standard_metrics.py. All reference masks are frozen.
#include "LpxQuality.h"
#include <algorithm>
#include <cmath>
#include <complex>
#include <numeric>

namespace lpx {
static constexpr double pi = 3.14159265358979323846;
static constexpr double nan = std::numeric_limits<double>::quiet_NaN();
using Complex = std::complex<double>;
static Complex twiddle512[512],twiddle640[640];
static bool fftPrepared;
static void prepareFft() {
    if(fftPrepared)return;
    for(int i=0;i<512;++i)twiddle512[i]=Complex(std::cos(-2*pi*i/512),std::sin(-2*pi*i/512));
    for(int i=0;i<640;++i)twiddle640[i]=Complex(std::cos(-2*pi*i/640),std::sin(-2*pi*i/640));
    fftPrepared=true;
}
static void fftPower2(Complex* x,int n) {
    for(int i=1,j=0;i<n;++i) { int bit=n>>1;for(;j&bit;bit>>=1)j^=bit;j^=bit;if(i<j)std::swap(x[i],x[j]); }
    for(int width=2;width<=n;width*=2) {
        for(int first=0;first<n;first+=width)for(int k=0;k<width/2;++k) {
            Complex w=twiddle512[k*512/width];
            Complex a=x[first+k],b=x[first+k+width/2]*w;
            x[first+k]=a+b;x[first+k+width/2]=a-b;
        }
    }
}
void periodogram(const double* input,int count,double* power,int n) {
    prepareFft();
    Complex data[640];
    if(n==640) {
        for(int part=0;part<5;++part) {
            for(int j=0;j<128;++j) { int at=j*5+part;data[part*128+j]=at<count?input[at]:0.; }
            fftPower2(data+part*128,128);
        }
        for(int k=0;k<=320;++k) {
            Complex sum=0.;
            for(int part=0;part<5;++part)sum+=data[part*128+k%128]*twiddle640[(part*k)%640];
            power[k]=std::norm(sum);
        }
    } else {
        for(int i=0;i<n;++i)data[i]=i<count?input[i]:0.;
        fftPower2(data,n);for(int i=0;i<=n/2;++i)power[i]=std::norm(data[i]);
    }
}
static double estimatePeriodScratch(const double* input,int count,double& rms,int rate,int last,
                                    double* x,double* difference,double* cmnd) {
    double mean=0,maximum=0,energy=0;
    for(int i=0;i<count;++i)mean+=input[i];mean/=count;
    for(int i=0;i<count;++i) { x[i]=input[i]-mean;energy+=x[i]*x[i];maximum=std::max(maximum,std::abs(x[i])); }
    rms=std::sqrt(energy/count);if(rms<.5)return nan;
    for(int i=0;i<count;++i)x[i]/=maximum;
    double denominator=0;
    for(int lag=1;lag<=last+1;++lag) {
        for(int i=0;i<count-last-1;++i) { double d=x[i]-x[i+lag];difference[lag]+=d*d; }
        denominator+=difference[lag];cmnd[lag]=denominator>std::numeric_limits<double>::min()?difference[lag]*lag/denominator:1;
    }
    for(int lag=std::max(2,rate/800);lag<=last;++lag)if(cmnd[lag]<=cmnd[lag-1] && cmnd[lag]<cmnd[lag+1] && cmnd[lag]<.15) {
        double left=difference[lag-1],middle=difference[lag],right=difference[lag+1];
        double curvature=left-2*middle+right;
        double offset=curvature>0?(left-right)/(2*curvature):0;
        double period=lag+std::max(-.5,std::min(.5,offset));double hz=rate/period;
        return hz>=50 && hz<=800?period:nan;
    }
    return nan;
}
double estimatePeriod(const double* input,int count,double& rms) {
    double x[640],difference[162]={},cmnd[162]={1};
    return estimatePeriodScratch(input,count,rms,8000,160,x,difference,cmnd);
}
double estimatePeriod(const double* input,int count,double& rms,int rate) {
    if(rate!=8000&&rate!=12000&&rate!=16000) {rms=0;return nan;}
    const int last=(rate+49)/50;
    if(count<=last+1||count>1280) {rms=0;return nan;}
    if(rate==8000&&count<=640)return estimatePeriod(input,count,rms);
    std::vector<double> x(count),difference(last+2),cmnd(last+2);cmnd[0]=1;
    return estimatePeriodScratch(input,count,rms,rate,last,x.data(),difference.data(),cmnd.data());
}
template<class Samples>
static void centeredWindow(const Samples& pcm,int start,int length,double* centered,double* power) {
    double mean=0;for(int i=0;i<length;++i)mean+=pcm[start+i];mean/=length;
    double windowed[640]={};
    for(int i=0;i<640;++i)centered[i]=i<length?pcm[start+i]-mean:0;
    for(int i=0;i<length;++i)windowed[i]=centered[i]*(length==1?1:.5-.5*std::cos(2*pi*i/(length-1)));
    periodogram(windowed,640,power,640);
}
static void bandShape(const double* power,double* shape) {
    double total=0;
    for(int b=0;b<32;++b) { shape[b]=0;for(int i=b*10+1;i<=b*10+10;++i)shape[b]+=power[i];total+=shape[b]; }
    for(int b=0;b<32;++b)shape[b]=total>0?std::sqrt(shape[b]/total):0;
}
static double fractionalError(const double* x,int support,double lag) {
    int whole=int(lag);double fraction=lag-whole,difference=0,energy=0;
    for(int i=0;i<support;++i) {
        double a=x[i],b=x[i+whole];if(fraction)b+=fraction*(x[i+whole+1]-b);
        double d=a-b;difference+=d*d;energy+=a*a+b*b;
    }
    return energy?difference/energy:1;
}
static double coarseShape(const double* powerA,const double* powerB) {
    double a[24]={},b[24]={},ta=0,tb=0,sum=0;
    for(int i=0;i<=320;++i) { int k=std::min(23,i*24/321);a[k]+=powerA[i];b[k]+=powerB[i];ta+=powerA[i];tb+=powerB[i]; }
    for(int i=0;i<24;++i) {
        double la=10*std::log10(std::max(1e-8,ta?a[i]/ta:0.));
        double lb=10*std::log10(std::max(1e-8,tb?b[i]/tb:0.));sum+=(la-lb)*(la-lb);
    }
    return std::sqrt(sum/24);
}
QualityContext::QualityContext(const Pcm& ref,bool assessSpeech,int rate,QualityTarget selectedTarget):reference(ref),target(selectedTarget),speech(assessSpeech),sampleRate(rate) {
    if(rate!=8000)analysisReference=qualityAnalysis8k(ref,rate);
    int count=rate==8000?int(ref.size()):int(analysisReference.size());
    for(int at=0;at+640<=count;at+=160) {
        double input[640],level;for(int j=0;j<640;++j)input[j]=rate==8000?ref[at+j]:analysisReference[at+j];
        periods.push_back(estimatePeriod(input,640,level));rms.push_back(level);
    }
}
Quality QualityContext::quality(const Pcm& candidate) const {
    Quality q;q.target=target;q.error[0]=sse(reference,candidate);
    if(speech)q.stoi[0]=stoi(reference,candidate,sampleRate);
    if(target==QualityTarget::Pwm) {
        const Pcm fixed=pwm(candidate);q.error[1]=sse(reference,fixed);
        if(speech)q.stoi[1]=stoi(reference,fixed,sampleRate);
    } else q.error[1]=std::numeric_limits<uint64_t>::max();
    return q;
}
bool noRegression(const Quality& q,const Quality& baseline) {
    if(q.target!=baseline.target || !validQualityTarget(q.target))return false;
    for(int i=0;i<qualityPathCount(q.target);++i)if(q.error[i]>baseline.error[i] || (std::isfinite(baseline.stoi[i]) && (!std::isfinite(q.stoi[i]) || q.stoi[i]<baseline.stoi[i]-1e-12)))return false;
    return true;
}
bool voiceGate(const Diagnostic& q,const Diagnostic& baseline) {
    if(q.within<baseline.within || q.collapsed>baseline.collapsed)return false;
    if(std::isfinite(baseline.period) && (!std::isfinite(q.period) || q.period>baseline.period+1e-12))return false;
    return !std::isfinite(baseline.shape) || (std::isfinite(q.shape) && q.shape<=baseline.shape+1e-12);
}
bool voiceGate(const Measurement& q,const Measurement& baseline) {
    if(q.quality.target!=baseline.quality.target || !validQualityTarget(q.quality.target))return false;
    for(int path=0;path<qualityPathCount(q.quality.target);++path)
        if(!voiceGate(q.diagnostic[path],baseline.diagnostic[path]))return false;
    return true;
}
template<class Samples>
static void assess8k(const Samples& reference,const Samples& candidate,const std::vector<double>& periods,const std::vector<double>& rms,double& voice,double& noise,Diagnostic& diagnostic) {
    int frames=0,voiced=0,noiseFrames=0,shapeFrames=0;double waveform=0,spectral=0,periodicity=0,shape=0,periodError=0,noiseCost=0;
    for(int at=0;at<int(reference.size());at+=160) {
        int length=std::min(640,int(reference.size())-at),index=at/160;
        double x[640],y[640],px[321],py[321],sx[32],sy[32];
        centeredWindow(reference,at,length,x,px);centeredWindow(candidate,at,length,y,py);
        double energy=0,loss=0;for(int i=0;i<length;++i) { energy+=double(reference[at+i])*reference[at+i];double d=double(candidate[at+i])-double(reference[at+i]);loss+=d*d; }
        waveform+=loss/std::max(energy,double(length));bandShape(px,sx);bandShape(py,sy);
        for(int i=0;i<32;++i)spectral+=(sx[i]-sy[i])*(sx[i]-sy[i]);
        double period=index<int(periods.size())?periods[index]:nan;
        if(std::isfinite(period)) {
            ++voiced;int support=length-int(std::ceil(2*period));
            for(int i=0;i<4;++i) { double lag=period*(.5+.5*i);double d=fractionalError(x,support,lag)-fractionalError(y,support,lag);periodicity+=d*d/4; }
            periodError+=fractionalError(y,length-int(period)-1,period);
        }
        if(length==640) {
            double input[640],level;for(int i=0;i<640;++i)input[i]=candidate[at+i];
            double actual=estimatePeriod(input,640,level);
            if(std::isfinite(period) && std::isfinite(actual) && std::abs(1200*std::log2(period/actual))<=100)++diagnostic.within;
            if(rms[index]>=.5) { ++shapeFrames;shape+=coarseShape(px,py);if(level<.5)++diagnostic.collapsed; }
        }
        if(length>=4) {
            ++noiseFrames;double totalX=0,totalY=0;
            for(int i=1;i<=320;++i) { totalX+=px[i];totalY+=py[i]; }
            if(totalX<=0) { double ac=0;for(int i=0;i<length;++i)ac+=y[i]*y[i];noiseCost+=std::min(1.,ac/length); }
            else if(totalY<=0)noiseCost+=1;
            else {
                int harmonics=std::isfinite(period)?int(std::floor(3800/(8000/period))):0;
                double ax[625]={},ay[625]={};
                for(int i=1;i<=320;++i) {
                    int label=harmonics+i-1;
                    if(harmonics) { double f=i*12.5,base=8000/period;int nearest=int(std::nearbyint(f/base));
                        if(nearest>=1 && nearest<=harmonics && std::abs(f-nearest*base)<=std::min(18.75,base/4))label=nearest-1;
                    }
                    ax[label]+=px[i];ay[label]+=py[i];
                }
                double hellinger=0,offX=0,offY=0;
                for(int i=0;i<320+harmonics;++i) { double a=ax[i]/totalX,b=ay[i]/totalY;double d=std::sqrt(a)-std::sqrt(b);hellinger+=d*d/2;if(i>=harmonics) { offX+=a;offY+=b; } }
                hellinger=std::max(0.,std::min(1.,hellinger));noiseCost+=harmonics?(hellinger+std::abs(offX-offY))/2:hellinger;
            }
        }
        ++frames;
    }
    voice=.25*waveform/frames+spectral/frames+2*periodicity/std::max(1,voiced);
    noise=noiseFrames?std::max(0.,std::min(1.,noiseCost/noiseFrames)):0;
    diagnostic.period=voiced?periodError/voiced:nan;diagnostic.shape=shapeFrames?shape/shapeFrames:nan;
}
void QualityContext::assess(const Pcm& candidate,double& voice,double& noise,Diagnostic& diagnostic) const {
    if(sampleRate==8000)assess8k(reference,candidate,periods,rms,voice,noise,diagnostic);
    else if(!analysisReference.empty())assess8k(analysisReference,qualityAnalysis8k(candidate,sampleRate),periods,rms,voice,noise,diagnostic);
    else voice=noise=nan;
}
Measurement QualityContext::measure(const Pcm& candidate) const {
    Measurement m;m.quality=quality(candidate);
    assess(candidate,m.voice[0],m.noise[0],m.diagnostic[0]);
    if(target==QualityTarget::Pwm) {
        const Pcm fixed=pwm(candidate);assess(fixed,m.voice[1],m.noise[1],m.diagnostic[1]);
        m.score=(m.voice[0]+m.noise[0]+m.voice[1]+m.noise[1])/2;
    } else {
        m.voice[1]=m.noise[1]=nan;
        m.score=m.voice[0]+m.noise[0];
    }
    for(int16_t sample:candidate)m.clipped+=sample<=-32768 || sample>=32767;
    return m;
}
}
