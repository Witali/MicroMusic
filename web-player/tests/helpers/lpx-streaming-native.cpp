#include "LpxStreaming.h"
#include "Lpx4HybridCore.h"
#include <cstdio>
#include <cstdlib>
#include <algorithm>

static bool decode(const std::vector<uint8_t>& bytes,const lpx::Pcm& expected,lpx::Pcm& actual) {
    Lpx4HybridCore core;if(!core.beginWideV9(bytes.data(),bytes.size()))return false;
    actual.resize(expected.size());for(size_t i=0;i<expected.size();++i)
        if(!core.nextS16(actual[i]) || actual[i]!=expected[i])return false;
    int16_t tail;return !core.nextS16(tail)&&!core.error()&&core.finished();
}
int main(int argc,char** argv) {
    if(argc!=7)return 1;
    const int profile=std::atoi(argv[1]),rate=std::atoi(argv[2]),normalization=std::atoi(argv[3]),target=std::atoi(argv[4]),maximum=std::atoi(argv[5]),calls=std::atoi(argv[6]);
    lpx::Pcm source;int low;while((low=std::getchar())!=EOF) {int high=std::getchar();if(high<0)return 2;source.push_back(int16_t(low|(high<<8)));}
    lpx::StreamingEncoder encoder(source.size(),profile,rate,0,calls,normalization!=0);if(encoder.status())return 3;
    if(normalization){
        for(size_t at=0;at<source.size();at+=lpx::kLpxStreamWindow){lpx::Pcm part(source.begin()+at,source.begin()+std::min(source.size(),at+lpx::kLpxStreamWindow));if(encoder.measure(part)<0)return 4;}
        if(encoder.plan(target,maximum)<0)return 5;
    }
    std::vector<uint8_t> body[2];lpx::Pcm expected[2];
    auto append=[&](const lpx::StreamingChunk& part){
        body[0].insert(body[0].end(),part.controlBytes.begin(),part.controlBytes.end());body[1].insert(body[1].end(),part.candidateBytes.begin(),part.candidateBytes.end());
        expected[0].insert(expected[0].end(),part.controlPcm.begin(),part.controlPcm.end());expected[1].insert(expected[1].end(),part.candidatePcm.begin(),part.candidatePcm.end());
    };
    for(size_t at=0;at<source.size();at+=lpx::kLpxStreamWindow){
        size_t stop=std::min(source.size(),at+lpx::kLpxStreamWindow);
        lpx::Pcm input(source.begin()+at,source.begin()+stop),future(source.begin()+stop,source.begin()+std::min(source.size(),stop+48));
        lpx::StreamingChunk part;if(encoder.process(input,future,part)<0)return 6;append(part);
    }
    lpx::StreamingChunk last;if(encoder.finish(last)<0)return 7;append(last);
    std::vector<uint8_t> complete[2];
    for(int kind=0;kind<(encoder.hasCandidate()?2:1);++kind){
        complete[kind]=encoder.getHeader(kind!=0);complete[kind].insert(complete[kind].end(),body[kind].begin(),body[kind].end());
        lpx::Pcm actual;if(!decode(complete[kind],expected[kind],actual))return 8;
        for(size_t at=0;at<actual.size();at+=lpx::kLpxStreamWindow)
            if(encoder.verifyPut(kind+1,at,actual.data()+at,std::min(size_t(lpx::kLpxStreamWindow),actual.size()-at))<0)return 9;
    }
    if(encoder.hasCandidate())for(size_t at=0;at<source.size();at+=lpx::kLpxStreamWindow)
        if(encoder.verifyPut(0,at,source.data()+at,std::min(size_t(lpx::kLpxStreamWindow),source.size()-at))<0)return 10;
    int choice=encoder.admit();if(choice<0)return 11;
    const auto report=encoder.loudness();std::fprintf(stderr,"{\"samples\":%u,\"choice\":%d,\"inputGainDb\":%.17g}\n",unsigned(source.size()),choice,report.gainDb);
    return std::fwrite(complete[choice].data(),1,complete[choice].size(),stdout)==complete[choice].size()?0:12;
}
