// Research-only native API driver. No private media or identities are embedded.
#include "LpxEncoder.h"
#include "LpxAdaptive.h"
#include "Lpx4HybridCore.h"
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>
#if defined(_WIN32)
#include <fcntl.h>
#include <io.h>
#endif

extern "C" {
int enc_adaptive_extended(int,int,int,int,int,int,int);
uint8_t* enc_adaptive_output();
int enc_adaptive_candidates();
int enc_adaptive_stages();
}

static void require(bool value) { if(!value)throw std::runtime_error("validation"); }
static void writeBytes(const char* name,const std::vector<uint8_t>& data) {
    std::ofstream out(name,std::ios::binary);require(bool(out));
    out.write(reinterpret_cast<const char*>(data.data()),data.size());require(bool(out));
}
struct DecodeReport { uint32_t samples;int rate; };
static DecodeReport decode(const std::vector<uint8_t>& bytes,const char* pcmPath,const char* pwmPath) {
    Lpx4HybridCore pcm,pwm;
    require(pcm.beginWideV9(bytes.data(),bytes.size())&&pwm.beginWideV9(bytes.data(),bytes.size()));
    require(pcm.samples()==pwm.samples()&&pcm.sampleRate()==pwm.sampleRate());
    const uint32_t samples=pcm.samples();
    std::vector<uint8_t> pcmBytes;pcmBytes.reserve(size_t(samples)*2);
    std::vector<uint8_t> pwmBytes;pwmBytes.reserve(samples);
    for(uint32_t i=0;i<samples;++i) {
        int16_t sample=0;uint8_t duty=0;
        require(pcm.nextS16(sample)&&pwm.next(duty));
        const int q14=(int(sample)+1)>>1;
        const int expected=std::max(0,std::min(255,128+((q14*130+8192)>>14)));
        require(duty==expected);
        pcmBytes.push_back(uint8_t(sample));pcmBytes.push_back(uint8_t(uint16_t(sample)>>8));
        pwmBytes.push_back(duty);
    }
    int16_t sample=0;uint8_t duty=0;
    require(!pcm.nextS16(sample)&&!pwm.next(duty)&&!pcm.error()&&!pwm.error()
        &&pcm.finished()&&pwm.finished()&&pcm.produced()==samples&&pwm.produced()==samples);
    writeBytes(pcmPath,pcmBytes);writeBytes(pwmPath,pwmBytes);
    return {samples,pcm.sampleRate()};
}
int main(int argc,char** argv) {
    try {
#if defined(_WIN32)
        _setmode(_fileno(stdin),_O_BINARY);_setmode(_fileno(stdout),_O_BINARY);
#endif
        const std::vector<uint8_t> input((std::istreambuf_iterator<char>(std::cin)),{});
        std::vector<uint8_t> bytes;int legacyCap=0,finalCap=0,candidates=0,stages=0;
        double seconds=0;DecodeReport report{};
        if(argc==4&&std::string(argv[1])=="decode") {
            bytes=input;report=decode(bytes,argv[2],argv[3]);finalCap=bytes.size();
        } else {
            require(argc==8&&std::string(argv[1])=="encode"&&!input.empty()&&!(input.size()%2));
            const std::string mode(argv[2]);const int rate=std::atoi(argv[3]);
            const int calls=std::atoi(argv[4]);legacyCap=std::atoi(argv[5]);
            const int samples=int(input.size()/2);lpx::Pcm target(samples);
            for(int i=0;i<samples;++i)target[i]=int16_t(uint16_t(input[i*2])|(uint16_t(input[i*2+1])<<8));
            require(enc_reserve(samples)==1);std::copy(target.begin(),target.end(),enc_input());
            const bool adaptive=mode=="p4"||mode=="p6";
            const int profile=mode=="p4"?4:6;const int kbps=mode=="k3"?3:mode=="k8"?8:0;
            require(adaptive||kbps);require(calls>=0&&calls<=4&&legacyCap>=0);
            if(adaptive) {
                if(!legacyCap) {
                    auto control=lpx::fitSeed(target,profile,rate,13926,false);
                    require(control.samples==samples);legacyCap=lpx::compactBytes(control);
                }
                finalCap=legacyCap-(22-(samples>64000?17:13));
            } else {require(rate==8000);finalCap=int(int64_t(samples)*kbps*1000/(8*rate));}
            std::copy(target.begin(),target.end(),enc_input());
            const auto start=std::chrono::steady_clock::now();
            const int count=adaptive?enc_adaptive_extended(samples,profile,rate,0,legacyCap,calls,0)
                                    :enc_bitrate(samples,kbps,rate,0,calls);
            seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
            require(count>0&&count<=finalCap);
            bytes.assign(enc_adaptive_output(),enc_adaptive_output()+count);
            candidates=enc_adaptive_candidates();stages=enc_adaptive_stages();
            report=decode(bytes,argv[6],argv[7]);
            require(report.samples==uint32_t(samples)&&report.rate==rate);
        }
        std::cout.write(reinterpret_cast<const char*>(bytes.data()),bytes.size());require(bool(std::cout));
        std::cerr<<"{\"schema\":1,\"samples\":"<<report.samples<<",\"sample_rate\":"<<report.rate
                 <<",\"file_bytes\":"<<bytes.size()<<",\"legacy_cap\":"<<legacyCap
                 <<",\"final_cap\":"<<finalCap<<",\"api_encode_seconds\":"<<seconds
                 <<",\"candidates\":"<<candidates<<",\"stages\":"<<stages
                 <<",\"native_decoder_exact\":true}\n";
        return 0;
    } catch(...) {std::cerr<<"{\"schema\":1,\"error\":1}\n";return 1;}
}
