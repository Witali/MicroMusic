/* Isolated vector primitives only; no C decoder execution.
 * Before-controller arithmetic follows Xiph 1.2.1; vendor COPYING applies. */
#include "wb_fold.h"
#include "zero_innovation.h"
extern const int8_t exc_10_16_table[160],exc_20_32_table[640];
int16_t low_fuse_out[42];
uint8_t low_fuse_indices[6];
volatile int32_t low_fuse_scale,low_fuse_gain;
volatile uint8_t low_fuse_mode,low_fuse_command,low_fuse_status;
/* Observe the inline production dispatch behind a test-only ABI boundary. */
SPEEX_NB3_STAGE void low_fuse_after(int16_t *exc,const uint8_t *indices,int32_t scale,int32_t g,uint8_t mode)
{speex_wb_excitation_low40_avr(exc,indices,scale,g,mode);}
SPEEX_NB3_STAGE void low_fuse_before(int16_t *exc,const uint8_t *indices,int32_t scale,int32_t g,uint8_t mode)
{
    const int8_t *table=mode==2?exc_10_16_table:exc_20_32_table;
    uint8_t vectors=mode==2?4:2,width=mode==2?10:20;
    for(uint8_t v=0;v<vectors;v++) {
        const int8_t *shape=table+width*(unsigned)indices[v];
        for(uint8_t at=0;at<width;at+=10)
            speex_avr_zero_innovation10(exc+width*v+at,shape+at,scale);
    }
    speex_wb_fold40_avr(exc,g);
}
int main(void)
{
    low_fuse_status=1;
    for(;;)if(low_fuse_command) {
        int16_t *out=low_fuse_out+1;const uint8_t *indices=low_fuse_indices+1;
        if(low_fuse_command==1)low_fuse_after(out,indices,low_fuse_scale,low_fuse_gain,low_fuse_mode);
        else if(low_fuse_command==2)speex_wb_excitation_low40_c(out,indices,low_fuse_scale,low_fuse_gain,low_fuse_mode);
        else if(low_fuse_command==3)low_fuse_before(out,indices,low_fuse_scale,low_fuse_gain,low_fuse_mode);
        else if(low_fuse_mode==2)speex_wb_excitation_nb2_40_avr(out,indices,low_fuse_scale,low_fuse_gain);
        else speex_wb_excitation_nb8_40_avr(out,indices,low_fuse_scale,low_fuse_gain);
        low_fuse_command=0;low_fuse_status=2;
    }
}
