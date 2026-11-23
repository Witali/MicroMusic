// Portable streaming windowed-sinc input preparation, independent of LPX search.
// Fixed storage, planar float input, mono PCM16 output; no runtime imports.
#include <stdint.h>
#include <math.h>
#include <stddef.h>
namespace {
constexpr int inputCapacity=4096,outputCapacity=16384,ringCapacity=8192,coefficientCapacity=65536;
float input[2*inputCapacity],ring[ringCapacity];
uint8_t raw[4*inputCapacity];
int16_t output[outputCapacity];double coefficients[coefficientCapacity];
int inRate,outRate,channels,radius,taps,phases,count;bool ended;
uint64_t received,nextOutput;
int gcd(int a,int b){while(b){int r=a%b;a=b;b=r;}return a;}
bool supported(int rate){const int rates[]={7350,7500,8000,11025,12000,16000,22050,24000,32000,44100,48000,64000,88200,96000};for(int r:rates)if(rate==r)return true;return false;}
float sample(int64_t at){if(at<0||uint64_t(at)>=received)return 0;return ring[uint64_t(at)%ringCapacity];}
int emit(bool final){
    const uint64_t total=(received*uint64_t(outRate)+inRate/2)/inRate;
    while(final?nextOutput<total:nextOutput*uint64_t(inRate)/outRate+radius<received){
        if(count>=outputCapacity)return -2;
        uint64_t numerator=nextOutput*uint64_t(inRate);int64_t center=numerator/outRate;
        int phase=int((numerator%outRate)/gcd(inRate,outRate));double sum=0;
        for(int j=0;j<taps;++j)sum+=sample(center-radius+j)*coefficients[phase*taps+j];
        if(!isfinite(sum))return -3;
        // Match the existing JavaScript PCM16 ties: Math.round is floor(x+.5).
        double value=floor(sum*32768.+.5);output[count++]=int16_t(value<-32768?-32768:value>32767?32767:value);++nextOutput;
    }
    return count;
}
}
extern "C" {
float* source_input(){return input;}
uint8_t* source_raw_input(){return raw;}
int source_copy_s16(int frames){
    if(!inRate||frames<0||frames>inputCapacity)return -1;
    for(int j=0;j<frames;++j)for(int c=0;c<channels;++c){int at=(j*channels+c)*2;int16_t value=int16_t(raw[at]|(int(raw[at+1])<<8));input[c*inputCapacity+j]=value/32768.f;}return frames;
}
int16_t* source_output(){return output;}
int source_capacity(){return inputCapacity;}
int source_init(int sourceRate,int targetRate,int channelCount){
    if(!supported(sourceRate)||(targetRate!=8000&&targetRate!=12000&&targetRate!=16000)||(channelCount!=1&&channelCount!=2))return -1;
    inRate=sourceRate;outRate=targetRate;channels=channelCount;received=nextOutput=0;count=0;ended=false;
    radius=int(ceil(24.*fmax(1.,double(inRate)/outRate)));taps=radius*2+1;phases=outRate/gcd(inRate,outRate);
    if(phases*taps>coefficientCapacity||radius*2+inputCapacity>=ringCapacity)return -1;
    const double pi=3.14159265358979323846,cutoff=.45*fmin(1.,double(outRate)/inRate);
    for(int phase=0;phase<phases;++phase){
        double fraction=double(phase)/phases,total=0;
        for(int j=0;j<taps;++j){double x=j-radius-fraction;double weight=.42+.5*cos(pi*x/(radius+1))+.08*cos(2*pi*x/(radius+1));
            double value=(fabs(x)<1e-14?2*cutoff:sin(2*pi*cutoff*x)/(pi*x))*weight;
            coefficients[phase*taps+j]=value;total+=value;
        }
        for(int j=0;j<taps;++j)coefficients[phase*taps+j]/=total;
    }
    return 1;
}
int source_push(int frames,int final){
    if(!inRate||ended||frames<0||frames>inputCapacity||(final!=0&&final!=1))return -1;
    count=0;
    // Emit as input arrives so circular storage never overwrites required history.
    for(int j=0;j<frames;++j){double value=0;for(int c=0;c<channels;++c){float x=input[c*inputCapacity+j];if(!isfinite(x))return -3;value+=x/channels;}
        ring[received++%ringCapacity]=float(value);if(emit(false)<0)return -2;
    }
    if(final){ended=true;if(emit(true)<0)return -2;}return count;
}
}
