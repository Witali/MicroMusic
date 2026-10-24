#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "lsp.h"
void reference_lsp(const spx_lsp_t *,spx_coef_t *,int,char *);
static uint32_t seed=0x31415926;
static uint32_t random32(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
int main(void)
{
    unsigned test;
    int order;
    for (order=8;order<=10;order+=2) for (test=0;test<240000;++test) {
        int i,j;
        spx_lsp_t angles[10];spx_coef_t a[10],b[10];
        union {uint64_t alignment;char bytes[4096];} arena;
        for(i=0;i<order;++i) angles[i]=(spx_lsp_t)(random32()%25737);
        if (test<120000) for(i=1;i<order;++i){
            spx_lsp_t v=angles[i];
            for(j=i;j && angles[j-1]>v;--j)angles[j]=angles[j-1];
            angles[j]=v;
        }
        reference_lsp(angles,a,order,arena.bytes);
        lsp_to_lpc(angles,b,order,arena.bytes);
        assert(memcmp(a,b,order*sizeof(*a))==0);
    }
    puts("PASS: 480000 exact upstream LSP conversions, orders 8 and 10");
    return 0;
}
