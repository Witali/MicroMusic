#include <stdint.h>
#include <vector>
#include <fstream>
#include <iostream>
#include <iterator>
#include "Lpx4HybridCore.h"
int main(int argc,char**argv){
 if(argc!=3)return 2;
 std::ifstream f(argv[1],std::ios::binary);
 std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(f)),std::istreambuf_iterator<char>());
 Lpx4HybridCore d;
 if(!d.begin(bytes.data(),(uint16_t)bytes.size()))return 3;
 std::ofstream o(argv[2],std::ios::binary);
 int16_t s;
 while(d.nextQ14(s)){
   const uint16_t u=(uint16_t)s;
   const char bytes[2]={(char)(u&0xff),(char)(u>>8)};
   o.write(bytes,2);
 }
 return (!d.finished()||!o.good())?4:0;
}
