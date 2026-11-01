#include "Lpx4HybridCore.h"
#include <stdint.h>

#ifdef _WIN32
#define TEST_API extern "C" __declspec(dllexport)
#else
#define TEST_API extern "C" __attribute__((visibility("default")))
#endif

struct Input {
    const uint8_t* bytes;
    uint32_t available, position, calls;
    int16_t failure;
};
static int16_t readInput(void* opaque){
    Input* input=static_cast<Input*>(opaque);
    ++input->calls;
    if(input->position>=input->available)return input->failure;
    return input->bytes[input->position++];
}

TEST_API uint32_t lpx_input_object_size(){return sizeof(Lpx4HybridCore);}
// mode0 ROM; 1 callback; 2 callback->ROM; 3 ROM->callback;
// 4 null callback; 5 failed callback->ROM. domain0 PCM16,1 PWM8.
TEST_API int lpx_input_decode(const uint8_t* bytes,uint16_t size,uint32_t available,
                             int16_t failure,uint8_t mode,uint8_t domain,
                             int16_t* pcm,uint8_t* pwm,uint32_t capacity,uint32_t* meta){
    Lpx4HybridCore decoder;
    Input input={bytes,available,0,0,failure};
    uint32_t prior=0;
#if LPX4_ENABLE_INPUT_CALLBACK
    if(mode==2 || mode==5){
        if(mode==5)input.available=1;
        decoder.beginStream(readInput,&input,size);
        uint8_t unused;
        if(mode==2)decoder.next(unused);
        prior=input.calls;
    }else if(mode==3){
        decoder.begin(bytes,size);
        uint8_t unused;decoder.next(unused);
    }
    const bool ok=(mode==1 || mode==3 || mode==4)
        ? decoder.beginStream(mode==4?0:readInput,&input,size) : decoder.begin(bytes,size);
#else
    if(mode!=0)return -1;
    const bool ok=decoder.begin(bytes,size);
#endif
    uint32_t produced=0;
    if(ok){
        while(produced<capacity){
            bool got;
            if(domain==0)got=decoder.nextS16(pcm[produced]);
            else got=decoder.next(pwm[produced]);
            if(!got)break;
            ++produced;
        }
    }
    meta[0]=ok;meta[1]=decoder.error();meta[2]=decoder.samples();
    meta[3]=decoder.produced();meta[4]=decoder.finished();
    meta[5]=input.calls;meta[6]=input.position;meta[7]=prior;
    return static_cast<int>(produced);
}
