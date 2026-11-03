/* Isolated HB1 interpolation candidates. This does not contain a decoder.
 * Original loop/margins follow speex_wb1.c and Xiph Speex 1.2.1 lsp.c;
 * vendor/speex-1.2.1/COPYING retains the BSD provenance.
 * Difference forms and omitted checks require the pinned HB1 codebook domain,
 * independently characterized by check_wb_interpolation.py. */
#include <stdint.h>

#ifndef PROBE_VARIANT
#define PROBE_VARIANT 0
#endif
#if PROBE_VARIANT < 0 || PROBE_VARIANT > 6
#error Unsupported isolated interpolation candidate
#endif

#define HOST_MAILBOX __attribute__((externally_visible, used))
int16_t probe_old[8] HOST_MAILBOX, probe_new[8] HOST_MAILBOX;
uint8_t probe_work[320] HOST_MAILBOX;
int16_t *probe_out HOST_MAILBOX;
uint8_t probe_sub HOST_MAILBOX;
volatile uint8_t probe_command, probe_status;

__attribute__((noinline, externally_visible))
void wb_probe_interpolate(int16_t *interp)
{
    unsigned i;
#if PROBE_VARIANT < 2
    for(i=0;i<8;i++) {
        int16_t a=probe_old[i],b=probe_new[i];
        switch(probe_sub) {
#if PROBE_VARIANT == 0
        case 0:interp[i]=a+((b>>2)-(a>>2));break;
        case 1:interp[i]=(a>>1)+(b>>1);break;
        case 2:interp[i]=b+((a>>2)-(b>>2));break;
#else
        case 0:interp[i]=a+((b-a)>>2);break;
        case 1:interp[i]=a+((b-a)>>1);break;
        case 2:interp[i]=b-((b-a)>>2);break;
#endif
        default:interp[i]=b;break;
        }
    }
#elif PROBE_VARIANT < 5
    /* Unswitch once per quarter. Keep both source arrays and the exact
     * separately rounded margin repair; no new persistent state. */
    switch(probe_sub) {
    case 0:
        for(i=0;i<8;i++)interp[i]=probe_old[i]+((probe_new[i]-probe_old[i])>>2);
        break;
    case 1:
        for(i=0;i<8;i++)interp[i]=probe_old[i]+((probe_new[i]-probe_old[i])>>1);
        break;
    case 2:
        for(i=0;i<8;i++)interp[i]=probe_new[i]-((probe_new[i]-probe_old[i])>>2);
        break;
    default:
        for(i=0;i<8;i++)interp[i]=probe_new[i];
        break;
    }
#else
    /* Quarter three is quarter one with its endpoint pointers exchanged.
     * Divisibility by sixteen makes floor(-delta/4) == -floor(delta/4).
     * This shares the quarter loop without per-word selection. */
    const int16_t *a=probe_old,*b=probe_new;
    uint8_t sub=probe_sub;
    if(sub==2){a=probe_new;b=probe_old;}
    if(sub==1) {
        for(i=0;i<8;i++)interp[i]=a[i]+((b[i]-a[i])>>1);
    } else if(sub==3) {
        for(i=0;i<8;i++)interp[i]=b[i];
    } else {
        for(i=0;i<8;i++)interp[i]=a[i]+((b[i]-a[i])>>2);
    }
#endif
#if PROBE_VARIANT < 3 || PROBE_VARIANT == 5
    if(interp[0]<410)interp[0]=410;
#endif
    if(interp[7]>25736-410)interp[7]=25736-410;
#if PROBE_VARIANT == 4 || PROBE_VARIANT == 6
    /* Explicitly specialize the finite margin positions, allowing the
     * compiler to remove loop tests as well as redundant repair checks. */
#define REPAIR_LO(i) if(interp[i]<interp[(i)-1]+410)interp[i]=interp[(i)-1]+410
#define REPAIR_HI(i) if(interp[i]>interp[(i)+1]-410)interp[i]=(interp[i]>>1)+((interp[(i)+1]-410)>>1)
    REPAIR_LO(1);REPAIR_HI(1);
    REPAIR_LO(2);REPAIR_HI(2);
    REPAIR_LO(3);
    REPAIR_HI(4);
    REPAIR_LO(5);REPAIR_HI(5);
    REPAIR_LO(6);REPAIR_HI(6);
#undef REPAIR_LO
#undef REPAIR_HI
#else
    for(i=1;i<7;i++) {
#if PROBE_VARIANT == 3
        if(i!=4 && interp[i]<interp[i-1]+410)interp[i]=interp[i-1]+410;
        if(i!=3 && interp[i]>interp[i+1]-410)interp[i]=(interp[i]>>1)+((interp[i+1]-410)>>1);
#else
        if(interp[i]<interp[i-1]+410)interp[i]=interp[i-1]+410;
        if(interp[i]>interp[i+1]-410)interp[i]=(interp[i]>>1)+((interp[i+1]-410)>>1);
#endif
    }
#endif
}

int main(void)
{
    probe_status=1;
    for(;;)if(probe_command) {
        wb_probe_interpolate(probe_out);
        probe_command=0;probe_status=2;
    }
}
