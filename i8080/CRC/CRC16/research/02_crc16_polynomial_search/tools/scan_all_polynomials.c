#include <stdint.h>
#include <stdio.h>
static int order16(unsigned p){ unsigned v=1; for(int k=1;k<=65535;k++){v=((v<<1)^((v&0x8000)?p:0)) & 65535; if(v==1) return k;} return 0; }
int main(void){puts("poly_hex,period_bits,low_popcount,has_x_plus_one,degree_low");for(unsigned p=1;p<65536;p+=2){unsigned per=order16(p);unsigned pop=__builtin_popcount(p);int deg=31-__builtin_clz(p);printf("0x%04X,%u,%u,%u,%d\n",p,per,pop,pop%2,deg);}return 0;}
