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
 Lpx4HybridCore core;
 if(!core.begin(bytes.data(),(uint16_t)bytes.size()))return 3;
 std::vector<uint8_t> q;
 uint8_t sample;
 while(core.next(sample))q.push_back((uint8_t)core.debugLastQ());
 if(!core.finished())return 4;
 std::ofstream o(argv[2],std::ios::binary);
 o.write((char*)q.data(),q.size());
 return 0;
}
