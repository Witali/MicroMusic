#pragma once
#include "LpxAdaptiveController.h"
#include "LpxPacking.h"
#include "LpxEncodingPolicy.h"
#include <memory>

namespace lpx {
static constexpr int kLpxStreamWindow=20480;
struct StreamingChunk {
    std::vector<uint8_t> controlBytes,candidateBytes;
    Pcm controlPcm,candidatePcm;
};
class StreamingEncoder {
    uint32_t total,done=0,measured=0;
    int profile,rate,allowance,calls,header,error=0;
    EncodingPolicy policy;
    const QualityTarget qualityTarget;
    bool normalize,planned=false,ended=false,candidateLive=true,accuracy=false;
    Stream controlContext,candidateContext;
    V9PacketWriter controlWriter{false},candidateWriter{false};
    LoudnessMeter sourceMeter,preparedMeter,controlMeter,candidateMeter;
    LoudnessReport level;
    Pcm verification[3];
    uint32_t received[3]={};
    int choice=-1;
    static Stream nextContext(const Stream& stream,const Pcm& source,
                              const std::vector<Coefficients>& co,const SynthesisState& state);
    Pcm scaled(const Pcm& source) const;
public:
    StreamingEncoder(uint32_t samples,int profile,int sampleRate,int allowance,
                     int calls,bool normalize,bool accuracy=false,
                     QualityTarget target=QualityTarget::Pwm);
    int measure(const Pcm& pcm);
    int plan(int targetLufs,int maxGainDb);
    int process(const Pcm& source,const Pcm& lookahead,StreamingChunk& output);
    int finish(StreamingChunk& output);
    std::vector<uint8_t> getHeader(bool candidate) const;
    bool hasCandidate() const { return candidateLive; }
    int status() const { return error; }
    uint32_t processed() const { return done; }
    uint64_t cap() const;
    int verifyPut(int kind,uint32_t offset,const int16_t* pcm,int count);
    int admit();
    LoudnessReport loudness() const;
};
}
