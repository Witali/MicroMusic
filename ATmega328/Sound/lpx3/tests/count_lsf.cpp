#include <stdio.h>
#include <stdint.h>
#include <vector>
#include <fstream>
#include <iterator>
#include "../src/Lpx3AvrCore.h"
struct Input {std::vector<uint8_t> bytes;};
static uint8_t read(void* c,uint16_t i){return ((Input*)c)->bytes[i];}
int main(int argc,char** argv){
 if(argc!=2)return 2;
 Input in;
 std::ifstream f(argv[1],std::ios::binary);
 in.bytes.assign(std::istreambuf_iterator<char>(f),std::istreambuf_iterator<char>());
 if(in.bytes.size()>65535)return 3;
 Lpx3AvrCore d;
 if(!d.begin(read,&in,(uint16_t)in.bytes.size()))return 4;
 uint8_t sample;
 while(d.next(sample)){}
 if(!d.finished())return 5;
 printf("samples=%lu polyConversions=%lu\n",(unsigned long)d.produced(),(unsigned long)d.lsfConverts());
 return 0;
}
