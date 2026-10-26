/* Shared 8/10-sample controller source, Xiph BSD provenance in short_pitch.h. */
_Static_assert(SPEEX_SHORT_VECTORS*SPEEX_SHORT_SIZE==40 && SPEEX_SHORT_SIZE<=10,
               "Short-pitch vector geometry must match the bounded kernels");
#if SPEEX_NB3_USE_AVR_ASM
static SPEEX_NB3_HOT SPEEX_NB3_NOINLINE
#else
static SPEEX_NB3_STAGE_O2
#endif
void SPEEX_SHORT_NAME(int16_t *out,const int16_t *exc,uint8_t pitch,
                               const uint8_t *input_indices,int32_t scale,unsigned index)
{
#if SPEEX_NB3_USE_AVR_ASM
    const uint8_t *indices=input_indices;
#else
    uint8_t indices[SPEEX_SHORT_VECTORS];
    for(unsigned k=0;k<SPEEX_SHORT_VECTORS;k++)indices[k]=input_indices[k];
#endif
    int8_t gains[3];
#if SPEEX_NB3_USE_AVR_ASM
    int16_t edge[3];
#else
    const int16_t high=(int16_t)(scale>>12),low=(int16_t)(scale&4095);
#endif
    const uint8_t first=pitch-1,second=2*pitch-1;
    uint8_t vector,j=0;
    gains[0]=(int8_t)(32+AVR_READ_I8(gain_cdbk_lbr+index+2));
    gains[1]=(int8_t)(32+AVR_READ_I8(gain_cdbk_lbr+index+1));
    gains[2]=(int8_t)(32+AVR_READ_I8(gain_cdbk_lbr+index));
    for(vector=0;vector<SPEEX_SHORT_VECTORS;vector++) {
        unsigned code=indices[vector];
        const int8_t *shape=SPEEX_SHORT_TABLE+SPEEX_SHORT_SIZE*code;
        uint8_t left=SPEEX_SHORT_SIZE;
        while(left) {
            const int16_t *in;
            uint8_t count;
            if(j<first) {
                in=exc+(int)j-pitch-1;count=first-j;
            } else if(j>pitch && j<second) {
                in=exc+(int)j-2*pitch-1;count=second-j;
            } else {
#if SPEEX_NB3_USE_AVR_ASM
                if(j==first) {
                    edge[0]=exc[-2];edge[1]=exc[-1];edge[2]=exc[-pitch];
                    in=edge;count=1;
                } else if(j==pitch) {
                    edge[0]=exc[-1];edge[1]=exc[-pitch];edge[2]=exc[1-pitch];
                    in=edge;count=1;
                } else if(j==second) {
                    edge[0]=exc[-2];edge[1]=exc[-1];edge[2]=0;
                    in=edge;count=1;
                } else if(j==second+1) {
                    edge[0]=exc[-1];edge[1]=0;edge[2]=0;
                    in=edge;count=1;
                } else {
                    /* The original tap rule has no remaining history. */
                    speex_avr_zero_innovation_n(out,shape,scale,left);
                    out+=left;shape+=left;j+=left;
                    break;
                }
#else
                int32_t adaptive;
                if(j==first)
                    adaptive=(int32_t)gains[0]*exc[-2]+(int32_t)gains[1]*exc[-1]+(int32_t)gains[2]*exc[-pitch];
                else if(j==pitch)
                    adaptive=(int32_t)gains[0]*exc[-1]+(int32_t)gains[1]*exc[-pitch]+(int32_t)gains[2]*exc[1-pitch];
                else if(j==second)
                    adaptive=(int32_t)gains[0]*exc[-2]+(int32_t)gains[1]*exc[-1];
                else if(j==second+1)
                    adaptive=(int32_t)gains[0]*exc[-1];
                else {
                    /* This form is faster in the whole AVR C decoder than
                     * the bounded byte-product variants (see short-tail reports). */
                    do {
                        *out++=speex_nb3_segment_finish_c(0,AVR_READ_I8(shape),high,low);
                        ++shape;++j;
                    } while(--left);
                    break;
                }
                *out++=speex_nb3_segment_finish_c(adaptive,AVR_READ_I8(shape),high,low);
                ++shape;++j;--left;
                continue;
#endif
            }
            if(count>left) count=left;
#if SPEEX_NB3_USE_AVR_ASM
            if (count==1)
                speex_avr_long_innovation1(out,in,shape,scale,gains);
            else
                speex_avr_long_innovation_n(out,in,shape,scale,gains,count);
#else
            speex_nb3_long_innovation10_c(out,in,shape,scale,gains,count);
#endif
            out+=count;shape+=count;j+=count;left-=count;
        }
    }
}
