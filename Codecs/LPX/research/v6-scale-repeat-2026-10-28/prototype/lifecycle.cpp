// Test-only probe. Derived and original project provenance remain applicable.
#include <stdint.h>
#include <stdio.h>
#include <vector>
#include <fstream>
#include <iterator>
#define private public
#include "Lpx4HybridCore.h"
#undef private

static bool drain(Lpx4HybridCore value, const std::vector<int16_t>& expected, size_t from){
 for(size_t i=from;i<expected.size();++i){
  int16_t out=123;
  if(!value.nextS16(out)||out!=expected[i]||value.produced()!=i+1)return false;
 }
 int16_t out=123;
 return value.finished()&&!value.nextS16(out)&&value.error()==Lpx4HybridCore::NONE&&value.produced()==expected.size();
}

int main(int argc,char** argv){
 if(argc!=2)return 1;
 std::ifstream input(argv[1],std::ios::binary);
 std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(input)),std::istreambuf_iterator<char>());
 Lpx4HybridCore decoder;
 if(decoder.lag_||decoder.blockStep_||!decoder.begin(bytes.data(),bytes.size())||decoder.lag_||decoder.produced())return 2;
 std::vector<int16_t> expected;
 int16_t out;
 while(decoder.nextS16(out))expected.push_back(out);
 if(expected.size()!=decoder.samples()||!decoder.finished()||decoder.error())return 3;
 const unsigned cuts[]={0,1,19,20,39,40,159,160,161,319,320,321};
 for(unsigned cut:cuts){
  if(cut>expected.size())continue;
  if(!decoder.begin(bytes.data(),bytes.size())||decoder.lag_||decoder.blockStep_)return 4;
  for(unsigned i=0;i<cut;i++)if(!decoder.nextS16(out)||out!=expected[i])return 5;
  if(cut&&decoder.lag_<18)return 6;
  Lpx4HybridCore copy=decoder;
  Lpx4HybridCore assigned;
  assigned=decoder;
  if(!drain(copy,expected,cut)||!drain(assigned,expected,cut)||!drain(decoder,expected,cut))return 7;
 }
 if(decoder.begin(0,0)||decoder.lag_||decoder.blockStep_||decoder.error()!=Lpx4HybridCore::BAD_HEADER)return 8;
 for(int i=0;i<4;i++)if(decoder.nextS16(out)||decoder.error()!=Lpx4HybridCore::BAD_HEADER)return 9;
 if(!decoder.begin(bytes.data(),bytes.size())||decoder.lag_||!drain(decoder,expected,0))return 10;
 std::vector<uint8_t> wrong=bytes;wrong[22]=2;
 if(decoder.begin(wrong.data(),wrong.size())||decoder.error()!=Lpx4HybridCore::UNSUPPORTED||decoder.lag_)return 11;
 for(int i=0;i<4;i++)if(decoder.nextS16(out)||decoder.error()!=Lpx4HybridCore::UNSUPPORTED)return 12;
 if(!decoder.begin(bytes.data(),bytes.size())||decoder.lag_||!drain(decoder,expected,0))return 13;
 printf("copy/reset/error/first-scale lifecycle exact; sizeof=%u\n",unsigned(sizeof(decoder)));
 return 0;
}
