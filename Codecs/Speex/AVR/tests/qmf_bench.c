/* Isolate QMF cost on the target ISA; this is not a complete WB decoder. */
#include <stdint.h>
#include "qmf_memory.h"
#ifdef __AVR__
volatile uint8_t qmf_command, qmf_status;
volatile uint16_t qmf_size;
int16_t qmf_pcm[640];
static int16_t low_history[32], high_history[32];
int main(void)
{
    qmf_status=1;
    for (;;) {
        while (qmf_command!=1) { }
        qmf_command=0;
        qmf_status=2;
        speex_avr_qmf_memory(qmf_pcm,qmf_size,low_history,high_history);
        qmf_status=3;
    }
}
#else
/* The independent oracle calls the untouched upstream QMF function. */
#include <stdio.h>
#include <stdlib.h>
#include "arch.h"
#include "filters.h"
static const int16_t h0[64]={
 2,-7,-7,18,15,-39,-25,75,35,-130,-41,212,38,-327,-17,483,
 -32,-689,124,956,-283,-1307,543,1780,-973,-2467,1733,3633,-3339,-6409,9059,30153,
 30153,9059,-6409,-3339,3633,1733,-2467,-973,1780,543,-1307,-283,956,124,-689,-32,
 483,-17,-327,38,212,-41,-130,35,75,-25,-39,15,18,-7,-7,2};
int main(int argc,char **argv)
{
    int16_t pcm[640],low[64]={0},high[64]={0};
    char scratch[4096];
    int i,n;
    FILE *input,*output;
    if (argc!=4) return 2;
    n=atoi(argv[1]); if (n!=320 && n!=640) return 2;
    input=fopen(argv[2],"rb");output=fopen(argv[3],"wb");
    if (!input || !output) return 3;
    while (fread(pcm,2,n,input)==(size_t)n) {
        qmf_synth(pcm,pcm+n/2,h0,pcm,n,64,low,high,scratch);
        for (i=0;i<n;++i) {
            fputc((uint16_t)pcm[i]&255,output);fputc((uint16_t)pcm[i]>>8,output);
        }
    }
    return fclose(output)!=0;
}
#endif
