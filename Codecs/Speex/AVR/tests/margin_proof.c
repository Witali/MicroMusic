/* Independent certificate maxima from untouched Xiph dequantization. */
#include <assert.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "speex/speex_bits.h"
#include "lsp.h"
#include "margin-certificates.h"
void proof_unquant(spx_lsp_t *,int,SpeexBits *);
int main(void)
{
    int32_t observed[MARGIN_CERTIFICATES];uint32_t n;unsigned i,j;
    int minimum=32767,maximum=-32768;
    for(j=0;j<MARGIN_CERTIFICATES;j++)observed[j]=INT32_MIN;
    for(n=0;n<(1u<<18);n++){
        uint8_t bytes[5]={0x39,(uint8_t)(n>>10),(uint8_t)(n>>2),(uint8_t)(n<<6),0x93},saved[5];
        int16_t raw[12];SpeexBits bits={0};memcpy(saved,bytes,sizeof(bytes));
        raw[0]=0x1357;raw[11]=0x2468;bits.chars=(char *)bytes+1;bits.nbBits=18;bits.buf_size=3;
        proof_unquant(raw+1,10,&bits);
        assert(bits.charPtr*8+bits.bitPtr==18 && !bits.overflow);
        for(i=1;i<=10;i++){
            assert(!(raw[i]&15) && raw[i]>=96 && raw[i]<=24880);
            if(raw[i]<minimum)minimum=raw[i];if(raw[i]>maximum)maximum=raw[i];
        }
        for(j=0;j<MARGIN_CERTIFICATES;j++){
            int32_t value=margin_certificates[j].constant;
            for(i=0;i<10;i++)value+=(int32_t)raw[i+1]*margin_certificates[j].weights[i];
            if(value>observed[j])observed[j]=value;
        }
        assert(raw[0]==0x1357 && raw[11]==0x2468 && !memcmp(bytes,saved,sizeof(bytes)));
    }
    for(j=0;j<MARGIN_CERTIFICATES;j++)assert(observed[j]==margin_certificates[j].maximum);
    assert(minimum==96 && maximum==24880);
    printf("{\"codeTriples\":262144,\"affineCertificates\":%u,\"affineValues\":%lu,"
        "\"minRaw\":96,\"maxRaw\":24880,\"endpointsMultiple16\":true,"
        "\"exactMaximaAgainstUntouchedXiph\":true,\"inputAndGuardsPreserved\":true}\n",
        (unsigned)MARGIN_CERTIFICATES,(unsigned long)(262144u*MARGIN_CERTIFICATES));
    return 0;
}
