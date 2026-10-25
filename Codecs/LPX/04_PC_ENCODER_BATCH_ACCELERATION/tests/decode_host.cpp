#include <stdint.h>
#include <vector>
#include <fstream>
#include <iostream>
#include <iterator>
#include "Lpx4HybridCore.h"
int main(int argc,char**argv){
 if(argc!=3){std::cerr<<"usage: decode_host <file.l4hy> <output.pcm8>\n";return 2;}
 std::ifstream f(argv[1],std::ios::binary);
 std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(f)),std::istreambuf_iterator<char>());
 Lpx4HybridCore c;
 if(!c.begin(bytes.data(),(uint16_t)bytes.size())){std::cerr<<"bad header "<<(int)c.error()<<"\n";return 3;}
 std::vector<uint8_t> pcm;
 pcm.reserve(c.samples());uint8_t x;
 while(c.next(x))pcm.push_back(x);
 if(!c.finished()){std::cerr<<"decode error "<<(int)c.error()<<" @ "<<c.produced()<<"\n";return 4;}
 std::ofstream o(argv[2],std::ios::binary);o.write((char*)pcm.data(),pcm.size());
 std::cout<<pcm.size()<<" samples\n";
 return 0;
}
