#define private public
#include "Lpx4HybridCore.h"
#undef private
#include <cmath>
#include <stdint.h>
struct Input{const uint8_t* bytes;uint32_t available,position,calls;int16_t failure;};
static int16_t reader(void* p){Input& in=*static_cast<Input*>(p);++in.calls;
    return in.position<in.available?in.bytes[in.position++]:in.failure;}
extern "C" uint32_t object_size(){return sizeof(Lpx4HybridCore);}
extern "C" int decode(const uint8_t* bytes,uint16_t size,uint32_t available,
                       int16_t failure,uint8_t mode,double* out,uint32_t capacity,
                       uint32_t* meta,double* diagnostics){
    Lpx4HybridCore d;Input input={bytes,available,0,0,failure};
#if LPX4_ENABLE_INPUT_CALLBACK
    if(mode==2||mode==5){if(mode==5)input.available=1;d.beginStream(reader,&input,size);
#if LPX4_FLOAT_SYNTHESIS
        double unused;d.nextFloat(unused);
#else
        int16_t unused;d.nextS16(unused);
#endif
    }else if(mode==3){d.begin(bytes,size);
#if LPX4_FLOAT_SYNTHESIS
        double unused;d.nextFloat(unused);
#else
        int16_t unused;d.nextS16(unused);
#endif
    }
    bool ok=(mode==1||mode==3||mode==4)?d.beginStream(mode==4?0:reader,&input,size):d.begin(bytes,size);
#else
    bool ok=d.begin(bytes,size);
#endif
    uint32_t count=0;double fraction=0;
    while(ok&&count<capacity){
#if LPX4_FLOAT_SYNTHESIS
        double sample=123.0;if(!d.nextFloat(sample)){if(sample!=123.0)return -9;break;}
        out[count++]=sample;
        const double state=d.prevDeemph_;
        const double frac=std::fabs(state-std::floor(state+0.5));
        if(frac>fraction)fraction=frac;
#else
        int16_t sample;if(!d.nextS16(sample))break;out[count++]=sample/32768.0;
#endif
    }
    meta[0]=ok;meta[1]=d.error();meta[2]=d.samples();meta[3]=d.produced();meta[4]=d.finished();
    meta[5]=input.calls;meta[6]=input.position;
    diagnostics[0]=fraction;diagnostics[1]=d.a_[0];diagnostics[2]=d.prevDeemph_;
    return count;
}
#if LPX4_FLOAT_SYNTHESIS
extern "C" int decode_adapter(const uint8_t* bytes,uint16_t size,uint8_t domain,
    double* output,uint32_t capacity,uint32_t* meta,double* finalState){
    Lpx4HybridCore d;const bool ok=d.begin(bytes,size);uint32_t count=0;
    while(ok&&count<capacity){
        bool got;double value;
        if(domain==0){got=d.nextFloat(value);}
        else if(domain==1){int16_t sample;got=d.nextS16(sample);value=sample;}
        else if(domain==2){uint8_t sample;got=d.next(sample);value=sample;}
        else{int16_t sample;got=d.nextQ14(sample);value=sample;}
        if(!got)break;output[count++]=value;
    }
    meta[0]=ok;meta[1]=d.error();meta[2]=d.finished();meta[3]=d.produced();
    finalState[0]=d.prevDeemph_;for(uint8_t i=0;i<10;++i)finalState[i+1]=d.hist_[i];
    return count;
}
#endif
