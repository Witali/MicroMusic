#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
static int64_t fw[65536];
unsigned powers[1024];
static uint64_t count4(unsigned poly,int n){
    for(int i=0;i<65536;i++)fw[i]=0;
    unsigned x=1;
    for(int i=0;i<n;i++) {powers[i]=x;x=((x<<1) ^ ((x&0x8000)?poly:0))&0xffff;}
    for(int i=0;i<n;i++)for(int j=i+1;j<n;j++)fw[powers[i]^powers[j]]++;
    uint64_t count=0;
    for(int v=0;v<65536;v++)count+=(fw[v]*(fw[v]-1))/2;
    if(count%3)fprintf(stderr,"non-disjoint pair collision: %u n%d count%llu\n",poly,n,(unsigned long long)count);
    return count/3;
}
int main(){int polys[]={0x7,0x9,0x1b,0x2d,0x31,0x39,0x3b,0x6b,0x79,0x1021,0x8005,0xa2eb};
for(int k=0;k<sizeof(polys)/sizeof(polys[0]);k++){unsigned p=polys[k];printf("0x%04X %llu %llu %llu\n",p,(unsigned long long)count4(p,128),(unsigned long long)count4(p,256),(unsigned long long)count4(p,1024));} }
