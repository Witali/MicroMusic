#include "LpxAdaptive.h"
#include "LpxQuality.h"
#include "LpxEncoder.h"
#include "LpxSeed.h"
#include "LpxAdaptiveController.h"
#include <stdio.h>
#include <stdlib.h>
#include <cmath>
#include <string.h>

int main(int argc,char** argv) {
    if(argc!=5)return 2;
    lpx::Pcm pcm;int lo;
    while((lo=getchar())!=EOF) { int hi=getchar();if(hi==EOF)return 3;pcm.push_back(int16_t(lo|(hi<<8))); }
    if(!enc_reserve(pcm.size()))return 4;
    bool adaptive=!strcmp(argv[3],"adaptive");lpx::AdaptiveReport report;
    auto stream=adaptive?lpx::adaptiveEncode(pcm,atoi(argv[1]),atoi(argv[2]),report,false,0,atoi(argv[4])):
        lpx::fitSeed(pcm,atoi(argv[1]),atoi(argv[2]),atoi(argv[3]),atoi(argv[4])!=0);
    if(adaptive && report.error)return 7;
    auto decoded=lpx::render(stream);auto actual=lpxSeedView();
    if(!adaptive)for(size_t i=0;i<decoded.size();++i)if(decoded[i]!=actual.pcm[i])return 5;
    if(!lpx::verifyStream(stream,decoded))return 8;
    auto bytes=lpx::packV9(stream);
    if(fwrite(bytes.data(),1,bytes.size(),stdout)!=bytes.size())return 6;
    lpx::QualityContext context(pcm);auto m=context.measure(decoded);
    if(adaptive)fprintf(stderr,"{\"candidates\":%d,\"selected\":%d,\"stages\":[%d,%d,%d,%d]}\n",report.candidates,report.selected,report.stageOperator[0],report.stageOperator[1],report.stageOperator[2],report.stageOperator[3]);
    fprintf(stderr,"{\"bytes\":%d,\"error\":[%llu,%llu],\"stoi\":[%.17g,%.17g],\"voice\":[%.17g,%.17g],\"noise\":[%.17g,%.17g],\"score\":%.17g,\"within\":[%d,%d],\"collapsed\":[%d,%d],\"period\":[%.17g,%.17g],\"shape\":[%.17g,%.17g]}\n",
        lpx::compactBytes(stream),(unsigned long long)m.quality.error[0],(unsigned long long)m.quality.error[1],m.quality.stoi[0],m.quality.stoi[1],m.voice[0],m.voice[1],m.noise[0],m.noise[1],m.score,m.diagnostic[0].within,m.diagnostic[1].within,m.diagnostic[0].collapsed,m.diagnostic[1].collapsed,m.diagnostic[0].period,m.diagnostic[1].period,m.diagnostic[0].shape,m.diagnostic[1].shape);
}
