#include "codec2_hybrid.h"
#include <assert.h>
#include <stdio.h>
int codec2_postfilter_init(codec2_hybrid *state);
int codec2_postfilter_decode(codec2_hybrid *state,const uint8_t *packet,size_t length,int16_t pcm[160]);
int main(int argc,char **argv){
    assert(argc==3);FILE *f=fopen(argv[1],"rb"),*out=fopen(argv[2],"wb");assert(f&&out);
    codec2_hybrid original,candidate;assert(!codec2_hybrid_init(&original)&&!codec2_postfilter_init(&candidate));
    uint8_t packet[8];int16_t a[160],b[160];unsigned frames=0,mismatches=0;int first=-1;size_t got;
    while((got=fread(packet,1,8,f))){assert(got==8);assert(!codec2_hybrid_decode(&original,packet,8,a)&&!codec2_postfilter_decode(&candidate,packet,8,b));
        assert(fwrite(b,2,160,out)==160);if(original.random_state!=candidate.random_state){if(first<0)first=(int)frames;++mismatches;}++frames;
    }
    assert(!ferror(f)&&!fclose(f)&&!fclose(out));
    printf("{\"frames\":%u,\"first_rng_mismatch_frame\":%d,\"frames_with_rng_mismatch\":%u}\n",frames,first,mismatches);return 0;
}
