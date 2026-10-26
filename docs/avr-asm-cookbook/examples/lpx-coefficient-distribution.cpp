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
 unsigned long zero[10]={0},small[10]={0},allZero=0,allSmall=0,wideCount[11]={0};
 for(int f=1;f<argc;f++){
  std::ifstream in(argv[f],std::ios::binary);std::vector<uint8_t> b((std::istreambuf_iterator<char>(in)),{});
  Lpx4HybridCore d;if(!d.begin(b.data(),b.size()))return 2;int16_t v;
  while(d.nextS16(v)){bool all=true;unsigned wide=0;for(unsigned i=0;i<10;i++){
   zero[i]+=d.a_[i]==0;small[i]+=d.a_[i]>=-128&&d.a_[i]<=127;all&=d.a_[i]==0;wide+=d.a_[i]<-128||d.a_[i]>127;
  }allZero+=all;allSmall+=wide==0;++wideCount[wide];}
  if(!d.finished())return 3;
 }
 printf("{\"zero\":[");for(unsigned i=0;i<10;i++)printf("%s%lu",i?",":"",zero[i]);
 printf("],\"signed8\":[");for(unsigned i=0;i<10;i++)printf("%s%lu",i?",":"",small[i]);
 printf("],\"all_zero_samples\":%lu,\"all_signed8\":%lu,\"wide_counts\":[",allZero,allSmall);
 for(unsigned i=0;i<11;i++)printf("%s%lu",i?",":"",wideCount[i]);
 printf("]}\n");
}
