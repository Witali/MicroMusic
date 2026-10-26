#include "codec2_hybrid.h"
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
int codec2_postfilter_init(codec2_hybrid *state);
int codec2_postfilter_decode(codec2_hybrid *state,const uint8_t *packet,size_t length,int16_t pcm[160]);
int main(int argc,char **argv){
    assert(argc==2);FILE *f=fopen(argv[1],"rb");assert(f);
    codec2_hybrid reference,candidate;assert(!codec2_hybrid_init(&reference)&&!codec2_postfilter_init(&candidate));
    uint8_t packet[8];int16_t a[160],b[160];unsigned frames=0,mismatches=0;int first=-1;size_t got;
    while((got=fread(packet,1,8,f))){assert(got==8);assert(!codec2_hybrid_decode(&reference,packet,8,a)&&!codec2_postfilter_decode(&candidate,packet,8,b));
        if(reference.random_state!=candidate.random_state){if(first<0)first=(int)frames;++mismatches;}++frames;
    }
    assert(!ferror(f)&&!fclose(f));
    printf("{\"frames\":%u,\"first_rng_mismatch_frame\":%d,\"frames_with_rng_mismatch\":%u,\"reference_final_rng\":%"PRIu32",\"candidate_final_rng\":%"PRIu32"}\n",frames,first,mismatches,reference.random_state,candidate.random_state);return 0;
}
