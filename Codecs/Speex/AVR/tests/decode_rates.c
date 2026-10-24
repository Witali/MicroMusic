/* Full upstream fixed-point oracle for native 8/16/32-kHz packets.
 * This PC harness is deliberately separate from the supported AVR NB3 API. */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include "speex/speex.h"
#include "speex/speex_bits.h"
int main(int argc, char **argv)
{
    unsigned char packet[2048];
    spx_int16_t pcm[640];
    spx_int32_t off=0, frame_size;
    int mode, bytes, i;
    size_t count;
    void *state;
    FILE *input, *output;
    SpeexBits bits;
    if (argc!=5) return 2;
    mode=atoi(argv[1]); bytes=atoi(argv[2]);
    if (mode<0 || mode>2 || bytes<1 || bytes>2048) return 2;
    input=fopen(argv[3],"rb"); output=fopen(argv[4],"wb");
    if (!input || !output) return 3;
    state=speex_decoder_init(speex_lib_get_mode(mode));
    if (!state) return 4;
    speex_decoder_ctl(state,SPEEX_SET_ENH,&off);
    speex_decoder_ctl(state,SPEEX_SET_HIGHPASS,&off);
    speex_decoder_ctl(state,SPEEX_GET_FRAME_SIZE,&frame_size);
    if (frame_size!=(160<<mode)) return 4;
    speex_bits_init_buffer(&bits,packet,sizeof(packet));
    while ((count=fread(packet,1,bytes,input))!=0) {
        if (count!=(size_t)bytes) return 5;
        speex_bits_set_bit_buffer(&bits,packet,bytes);
        if (speex_decode_int(state,&bits,pcm) || bits.overflow) return 6;
        for (i=0;i<frame_size;++i)
            if (fputc((uint16_t)pcm[i]&255,output)==EOF ||
                fputc((uint16_t)pcm[i]>>8,output)==EOF) return 7;
    }
    if (ferror(input) || fclose(output)) return 8;
    fclose(input); speex_bits_destroy(&bits); speex_decoder_destroy(state);
    return 0;
}
