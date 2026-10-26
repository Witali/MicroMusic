#include <stdint.h>
#include <stdio.h>
#include <fstream>
#include <iterator>
#include <vector>
#define private public
#include "Lpx4HybridCore.h"
#undef private
#include "Lpx4HybridCore.cpp"
int main(int argc,char** argv){
 unsigned long gains[32]={0},mode0=0,zeroX=0;
 for(int f=1;f<argc;f++){
  std::ifstream in(argv[f],std::ios::binary);std::vector<uint8_t> blob((std::istreambuf_iterator<char>(in)),{});
  Lpx4HybridCore d;if(!d.begin(blob.data(),blob.size()))return 2;
  int16_t v;while(d.nextS16(v))if(d.subType_){
   ++gains[d.gain_];mode0+=!d.mode_;
   zeroX+=!d.ringQ_[(uint8_t)(d.ringCursor_-1-d.lag_)];
  }
  if(!d.finished())return 3;
 }
 printf("{\"gains\":[");for(unsigned i=0;i<32;i++)printf("%s%lu",i?",":"",gains[i]);
 printf("],\"mode0\":%lu,\"zero_x\":%lu}\n",mode0,zeroX);
}
