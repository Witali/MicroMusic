#include <stdint.h>
#include <vector>
#include <fstream>
#include <iostream>
#include <iterator>
#include "Lpx4HybridCore.h"
int main(int argc,char**argv){
 if(argc!=3){std::cerr<<"usage: decode_s16_host <file.l4hy> <output.pcm16le>\n";return 2;}
 std::ifstream f(argv[1],std::ios::binary);
 std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(f)),std::istreambuf_iterator<char>());
 Lpx4HybridCore d;
 if(!d.begin(bytes.data(),(uint16_t)bytes.size()))return 3;
 std::ofstream o(argv[2],std::ios::binary);
 int16_t s;
 uint32_t count=0;
 while(d.nextS16(s)){
   uint16_t u=(uint16_t)s;
   const char v[2]={(char)(u&0xff),(char)(u>>8)};
   o.write(v,2);++count;
 }
 if(!d.finished()||!o.good()){std::cerr<<"decode error "<<(int)d.error()<<" at "<<d.produced()<<"\n";return 4;}
 std::cout<<count<<" samples (s16le)\n";
 return 0;
}
