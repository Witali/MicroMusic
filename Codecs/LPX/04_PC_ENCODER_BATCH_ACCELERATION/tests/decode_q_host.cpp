#include <stdint.h>
#include <vector>
#include <fstream>
#include <iostream>
#include <iterator>
#include "Lpx4HybridCore.h"
int main(int argc,char**argv){
 if(argc!=4){std::cerr<<"usage: decoder input.l4hy pcm_output.bin q_output.bin\n";return 2;}
 std::ifstream f(argv[1],std::ios::binary);
 std::vector<uint8_t> data((std::istreambuf_iterator<char>(f)),std::istreambuf_iterator<char>());
 Lpx4HybridCore c;
 if(!c.begin(data.data(),(uint16_t)data.size()))return 3;
 std::vector<uint8_t> pcm,exc;
 uint8_t p;
 while(c.next(p)){pcm.push_back(p);exc.push_back((uint8_t)c.debugLastQ());}
 if(!c.finished())return 4;
 std::ofstream o(argv[2],std::ios::binary),q(argv[3],std::ios::binary);
 o.write((const char*)pcm.data(),pcm.size());q.write((const char*)exc.data(),exc.size());
 return 0;
}
