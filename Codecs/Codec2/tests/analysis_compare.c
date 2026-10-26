#include "codec2_hybrid.h"
#include "fixed_analysis.h"
#include <assert.h>
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
int codec2_analysis_candidate_init(codec2_hybrid *state);
int codec2_analysis_candidate_decode(codec2_hybrid *state,const uint8_t *packet,size_t length,int16_t pcm[160]);
static double signal,noise,maximum,relative_power,minimum_norm=DBL_MAX,maximum_l1;
static unsigned calls;
void codec2_analysis_probe(compact_transform *buffer,const float coefficients[11]){
    compact_transform reference;compact_forward_lpc(&reference,coefficients);codec2_analysis_forward(buffer,coefficients);++calls;
    double l1=0;for(unsigned i=0;i<11;++i)l1+=fabs(coefficients[i]);maximum_l1=fmax(maximum_l1,l1);
    for(unsigned i=0;i<257;++i){
        double rr=reference.frequency[i].r,ri=reference.frequency[i].i,r=buffer->frequency[i].r,im=buffer->frequency[i].i;
        double norm=rr*rr+ri*ri,dr=r-rr,di=im-ri;assert(isfinite(r)&&isfinite(im));
        signal+=norm;noise+=dr*dr+di*di;maximum=fmax(maximum,fmax(fabs(dr),fabs(di)));minimum_norm=fmin(minimum_norm,norm);
        relative_power=fmax(relative_power,fabs((r*r+im*im+1e-6)/(norm+1e-6)-1));
    }
}
int main(int argc,char **argv){
    assert(argc==3);FILE *f=fopen(argv[1],"rb"),*out=fopen(argv[2],"wb");assert(f&&out);
    codec2_hybrid original,candidate;assert(!codec2_hybrid_init(&original)&&!codec2_analysis_candidate_init(&candidate));
    uint8_t packet[8];int16_t a[160],b[160];unsigned frames=0,mismatches=0;int first=-1;size_t got;
    while((got=fread(packet,1,8,f))){
        assert(got==8);assert(!codec2_hybrid_decode(&original,packet,8,a)&&!codec2_analysis_candidate_decode(&candidate,packet,8,b));
        assert(fwrite(b,2,160,out)==160);if(original.random_state!=candidate.random_state){if(first<0)first=(int)frames;++mismatches;}++frames;
    }
    assert(!ferror(f)&&!fclose(f)&&!fclose(out));
    char snr[64];if(noise==0)strcpy(snr,"null");else snprintf(snr,sizeof(snr),"%.12g",10*log10(signal/noise));
    printf("{\"frames\":%u,\"first_rng_mismatch_frame\":%d,\"frames_with_rng_mismatch\":%u,\"analysis_vectors\":%u,\"spectrum_snr_db\":%s,\"spectrum_max_absolute_error\":%.12g,\"minimum_reference_magnitude\":%.12g,\"maximum_regularized_power_relative_error\":%.12g,\"maximum_coefficient_l1\":%.12g}\n",
           frames,first,mismatches,calls,snr,maximum,sqrt(minimum_norm),relative_power,maximum_l1);
    return 0;
}
