/* Exhaust packet fields using an independent bit writer and the C reader. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "nb3_subframe.h"

static unsigned cases;
static void field(uint8_t *p,unsigned *bit,unsigned width,unsigned value)
{
    while (width--) {
        const unsigned mask=1u<<(7-(*bit&7));
        p[*bit>>3]=(p[*bit>>3]&~mask)|(((value>>width)&1)?mask:0);
        ++*bit;
    }
}
static void check(unsigned sub,unsigned header,unsigned word)
{
    uint8_t p[22],saved[22],out[6]={0xa5,0,0,0,0,0x5a};
    unsigned bit=28+33*sub,i;
    memset(p,0x69,sizeof(p));p[1]=24|(p[1]&7);
    field(p+1,&bit,13,header);field(p+1,&bit,20,word);
    memcpy(saved,p,sizeof(p));
    assert(speex_nb3_unpack_subframe(p+1,(uint8_t)sub,out+1)==header);
    for (i=0;i<4;i++) assert(out[i+1]==((word>>(15-5*i))&31));
    assert(out[0]==0xa5 && out[5]==0x5a);
    assert(!memcmp(p,saved,sizeof(p)));cases++;
}
int main(void)
{
    unsigned sub,word;
    for (sub=0;sub<4;sub++) {
        for (word=0;word<(1u<<20);word++)
            check(sub,(word*8191u+(word>>3))&8191,word);
        for (word=0;word<8192;word++)check(sub,word,(word*0x9e3779b9u)&0xfffff);
    }
    assert(cases==4227072);
    printf("PASS: %u packet groups; every 20-bit index group and 13-bit header at all four subframes\n",cases);
    return 0;
}
