#include "LpxLoudness.h"
#include <cstdio>
#include <cstdlib>
#include <cmath>
int main(int argc,char** argv) {
    if(argc!=2 && argc!=4)return 1;lpx::Pcm pcm;int lo;
    while((lo=getchar())!=EOF) { int hi=getchar();if(hi==EOF)return 2;pcm.push_back(int16_t(lo|(hi<<8))); }
    auto report=argc==2?lpx::normalizeLoudness(pcm,atoi(argv[1])):lpx::normalizeLoudness(pcm,atoi(argv[1]),atoi(argv[2]),atoi(argv[3]));
    if(fwrite(pcm.data(),2,pcm.size(),stdout)!=pcm.size())return 3;
    fprintf(stderr,"%d %d %.17g %.17g %.17g\n",report.status,report.limited,report.input,report.prepared,report.gainDb);
}
