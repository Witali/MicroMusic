/* Variable-size API mailbox: independent continuous mixed-mode/error tests. */
#include "speex_avr.h"
#include "speex_wb1.h"
#include <stdint.h>
#include <stddef.h>
uint8_t low_api_packet[32];
volatile uint8_t low_api_bytes,low_api_flags,low_api_command,low_api_status,low_api_chunks;
volatile int8_t low_api_result;
#if SPEEX_TEST_WIDEBAND
const int16_t *volatile low_api_pcm;
static void sink(const int16_t *pcm,uint8_t n,void *context)
{(void)n;(void)context;low_api_pcm=pcm;++low_api_chunks;}
#define INIT speex_wb1_init
#else
int16_t low_api_pcm[160];
#define INIT speex_avr_init
#endif
int main(void)
{
    INIT();low_api_status=1;
    for(;;) {
        if(low_api_command==2){INIT();low_api_command=0;low_api_status=1;}
        else if(low_api_command==1) {
            const uint8_t *packet=low_api_flags&1?NULL:low_api_packet;
#if SPEEX_TEST_WIDEBAND
            low_api_result=speex_wb1_decode(packet,low_api_bytes,low_api_flags&2?NULL:sink,NULL);
#else
            low_api_result=speex_avr_decode(packet,low_api_bytes,low_api_flags&2?NULL:low_api_pcm);
#endif
            low_api_command=0;low_api_status=2;
        }
    }
}
