#include <stdint.h>
#include <fstream>
#include <vector>
#include <iostream>
#include <iterator>
#include <algorithm>
#include "Lpx4HybridCore.h"
#ifndef LPX3_COST_INSTRUMENT
#error Compile with -DLPX3_COST_INSTRUMENT=1
#endif
int main(int argc,char **argv) {
 if(argc!=2) return 2;
 std::ifstream f(argv[1],std::ios::binary);
 std::vector<uint8_t> bin((std::istreambuf_iterator<char>(f)),std::istreambuf_iterator<char>());
 Lpx4HybridCore dec;
 if(!dec.begin(bin.data(),(uint16_t)bin.size()))return 3;
 uint32_t max_one=0,max_w80=0,max_w160=0;
 uint32_t s80=0,s160=0,n=0;
 uint16_t hist[160]={0};uint8_t x;
 // Evaluate rolling activity without any dependency on PWM or host timing.
 n=0;uint32_t prev=0;std::fill(hist,hist+160,0);
 while(dec.next(x)){
   uint32_t now=dec.bitCalls();uint32_t calls=now-prev;prev=now;
   uint16_t pos=n%160;
   if(n>=80)s80-=hist[(n-80)%160];
   if(n>=160)s160-=hist[pos];
   hist[pos]=(uint16_t)calls;s80+=calls;s160+=calls;
   max_one=std::max(max_one,calls);
   max_w80=std::max(max_w80,s80);
   max_w160=std::max(max_w160,s160);
   n++;
 }
 if(!dec.finished())return 5;
 std::cout<<"{\"samples\":"<<n<<",\"bit_calls\":"<<dec.bitCalls()
    <<",\"max_bit_calls_sample\":"<<max_one
    <<",\"max_bit_calls_80\":"<<max_w80
    <<",\"max_bit_calls_160\":"<<max_w160
    <<",\"rom_reads\":"<<dec.romByteCalls()
    <<",\"lsf_converts\":"<<dec.lsfConverts()<<"}\n";
 return 0;
}
