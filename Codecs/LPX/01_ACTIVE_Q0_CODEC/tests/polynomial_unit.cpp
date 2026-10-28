// Exact original rounded recurrence, checked against the compiled helper.
#define private public
#include "Lpx4HybridCore.cpp"
#include <stdio.h>
#include <string.h>

static int32_t floorShift(int64_t value,uint8_t bits){
    return value<0?-(int32_t)((-value+((1LL<<bits)-1))>>bits):(int32_t)(value>>bits);
}
static int32_t referenceProduct(int32_t value,int16_t coefficient){
    if(value<=250000L && value>=-250000L)return floorShift((int64_t)value*coefficient,12);
    const int32_t high=value/16; // original truncation towards zero
    const int32_t remainder=value-high*16;
    return floorShift((int64_t)high*coefficient,8)+floorShift((int64_t)remainder*coefficient,12);
}
static void referenceFactor(int32_t* p,int16_t c,uint8_t n){
    p[n+1]=p[n-1];
    p[n]=p[n-2]+referenceProduct(p[n-1],c);
    for(uint8_t j=n-1;j>=2;--j)p[j]=p[j-2]+referenceProduct(p[j-1],c)+p[j];
    p[1]+=c;
}
static uint32_t randomState=20261028UL;
static uint32_t randomWord(){randomState=randomState*1664525UL+1013904223UL;return randomState;}
static bool check(Lpx4HybridCore& core,int32_t* values,int16_t c,uint8_t n){
    int32_t actual[14],expected[14];
    memcpy(actual,values,sizeof actual);memcpy(expected,values,sizeof expected);
    core.polyFactor(actual+1,c,n);referenceFactor(expected+1,c,n);
    return !memcmp(actual,expected,sizeof actual);
}
int main(){
    Lpx4HybridCore core;uint32_t cases=0;
    // Both trailing units and every signed16 c; all other products stay bounded.
    for(uint8_t n=4;n<=10;n+=2)for(uint8_t sign=0;sign<2;sign++){
        for(int32_t c=-32768;c<=32767;c++){
            int32_t p[14]={1234567,4096};p[13]=-1234567;p[n]=sign?-4096:4096;
            if(!check(core,p,(int16_t)c,n))return 1;++cases;
        }
    }
    // Ordinary and split-floor products, with the valid cosine coefficient bound.
    for(uint16_t trial=0;trial<10000;trial++)for(uint8_t n=4;n<=10;n+=2){
        int32_t p[14]={1234567,4096};p[13]=-1234567;
        for(uint8_t i=1;i<n-1;i++)p[i+1]=(int32_t)(randomWord()%4000001UL)-2000000L;
        p[n]=(trial&1)?-4096:4096;
        const int16_t c=(int16_t)(randomWord()%16385UL)-8192;
        if(!check(core,p,c,n))return 2;++cases;
    }
    printf("%lu polynomial factors exact\n",(unsigned long)cases);
}
