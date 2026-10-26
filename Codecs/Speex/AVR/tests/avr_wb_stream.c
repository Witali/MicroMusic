/* SRAM-fed test application. Reuse the production IRQ, queue and conversion;
 * only input delivery and diagnostic capture differ. No transport is claimed. */
#define main speex_embedded_player_unused_main
#include "../src/wb_player.c"
#undef main

volatile uint16_t stream_packet_address,stream_pwm_address;
const int16_t *volatile stream_pcm;
volatile uint8_t stream_command,stream_status,stream_last,stream_chunks,stream_samples;
static __attribute__((noinline,noclone)) void stream_output(const int16_t *pcm,uint8_t count,void *context)
{
    stream_pcm=pcm;stream_samples=count;++stream_chunks;
    output(pcm,count,context);
}
int main(void)
{
    /* Same hardware initialization as src/wb_player.c; all addresses derive
     * from the manufacturer's avr/io.h, including the host's PWM hook. */
    cli();DDRB|=(1<<PB1);OCR1A=128;
    TCCR1A=(1<<COM1A1)|(1<<WGM10);TCCR1B=(1<<WGM12)|(1<<CS10);
    TCCR2A=(1<<WGM21);OCR2A=124;speex_wb1_init();
    stream_packet_address=(uint16_t)(uintptr_t)packet;
    stream_pwm_address=_SFR_MEM_ADDR(OCR1AL);
    for(;;) {
        stream_status=1;while(!stream_command){}
#if defined(SPEEX_AVR_FRAME_LOAD_CYCLES) && SPEEX_AVR_FRAME_LOAD_CYCLES > 0
        speex_player_frame_load();
#endif
        /* A volatile address prevents LTO assuming an unchanged dummy input;
         * the host fills this RAM packet before publishing the command. */
        const uint8_t *next=(const uint8_t *)(uintptr_t)stream_packet_address;
        if(speex_wb1_decode(next,SPEEX_SAMPLE_PACKET_BYTES,stream_output,0)) {
            speex_player_error=1;break;
        }
        stream_command=0;stream_status=2;if(stream_last)break;
    }
    input_finished=1;if(!speex_player_started)speex_player_done=1;
    while(!speex_player_done){}
    for(;;){}
}
