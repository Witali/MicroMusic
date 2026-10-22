/* Independent host execution of the *same C source*, with PIC SFR stubs.
 * It deliberately does NOT claim to emulate PIC machine-cycle timings.
 * Use to verify the browser sound model sample-for-sample.
 */
#include <stdio.h>
#include <stdlib.h>
#define main pic_firmware_main
#include "../firmware/main.c"
#undef main
int main(int argc,char**argv){
    long frames= argc>1 ? strtol(argv[1],0,10):15625;
    read_index=write_index=underruns=0;
    music_divider=envelope_ticks=remaining_grid=section_index=score_offset=0;
    grid_phase=0;drum_env=beat_index=0;
    drum_lfsr=0xace1;drum_phase=0;
    for(int i=0;i<3;i++){
        voice[i].phase=voice[i].step=0;
        voice[i].env=voice[i].stage=voice[i].age=voice[i].decay=voice[i].frame=0;
    }
    advance_event();
    for(long i=0;i<frames;i++){
        unsigned char v=generate_sample();putchar(v);

    }
    return 0;
}
