/* Cache lifetime observation only; production decoding and arithmetic unchanged. */
#include "speex_wb1.h"
#include "wb_internal.h"
#include "nb_celp.h"
#include <stddef.h>
#include <stdint.h>

uint8_t cache_packet[32];
volatile uint8_t cache_bytes,cache_command,cache_status,cache_chunks;
volatile int8_t cache_result;
volatile uint16_t cache_begin,cache_live_begin,cache_frame_begin,cache_move_begin,cache_seed;
const int16_t *volatile cache_pcm;
static void sink(const int16_t *samples,uint8_t count,void *context)
{(void)count;(void)context;cache_pcm=samples;++cache_chunks;}
int main(void)
{
    speex_wb1_init();
    uintptr_t base=(uintptr_t)speex_wb_noise_cache();
    cache_begin=base;
    cache_live_begin=base+2*(NB_DEC_EXC_OFFSET-NB_SUBFRAME_SIZE);
    cache_frame_begin=base+2*NB_DEC_EXC_OFFSET;
    cache_move_begin=base+2*NB_FRAME_SIZE;
    cache_seed=base- offsetof(DecState,excBuf)+offsetof(DecState,seed);
    cache_status=1;
    for(;;) {
        if(cache_command==2) {
            speex_wb1_init();cache_command=0;cache_status=1;
        } else if(cache_command==1) {
            cache_result=speex_wb1_decode(cache_packet,cache_bytes,sink,0);
            cache_command=0;cache_status=2;
        }
    }
}
