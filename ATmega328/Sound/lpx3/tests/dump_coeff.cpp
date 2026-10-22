#include "../src/Lpx3AvrCore.h"
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <cstdint>
#include <fstream>
#include <iterator>
static uint8_t get(void*ctx,uint16_t pos){return (*(const std::vector<uint8_t>*)ctx)[pos];}
int main(int argc,char**argv){
 if(argc!=3)return 2;
 std::ifstream s(argv[1],std::ios::binary);
 std::vector<uint8_t>d((std::istreambuf_iterator<char>(s)),{});
 Lpx3AvrCore a;
 if(!a.begin(get,&d,(uint16_t)d.size()))return 3;
 FILE*o=fopen(argv[2],"w");if(!o)return 4;
 uint8_t v;unsigned k=0;while(a.next(v)){
   if(k%20==0){int16_t c[10];a.copyCoefficients(c);fprintf(o,"%u",k);for(int i=0;i<10;i++)fprintf(o,",%d",c[i]);fprintf(o,"\n");}
   ++k;
 }
 fclose(o);return a.error()?5:0;
}
