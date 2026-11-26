#pragma once
#include "LpxAdaptive.h"
#include <string>

namespace lbg1 {
struct EncoderOptions {
    bool groupedBfp=false;
    bool trajectories=false;
    int coefficientError=0;
    double levelErrorDb=0;
};
struct EncoderStats {
    uint64_t spectrumBits=0,scaleBits=0,pitchBits=0,pulseBits=0,extraBits=0;
    uint64_t planCounts[4]={},widthCounts[7]={},exponentCounts[16]={};
    uint64_t scaleCommands[4]={},pitchCommands[4]={};
    int repeatFrames=0,repeatAnchors=0,forcedRawFrames=0;
    int coefficientMaxError=0,changedCoefficients=0;
    double maximumLevelErrorDb=0;
};
struct EncoderResult {
    std::vector<uint8_t> bytes;
    lpx::Pcm pcm; // Independent integer reference, not decoder replay.
    std::vector<lpx::Coefficients> coefficients;
    std::vector<int> excitationSteps;
    EncoderStats stats;
};
struct PulseRefitStats {uint64_t evaluations=0;int changedPulses=0,lookahead=160;};
EncoderResult encode(const lpx::Stream& source,const EncoderOptions& options);
lpx::Stream refitPulses(const lpx::Stream& source,const EncoderResult& decodedParameters,
                       const lpx::Pcm& reference,PulseRefitStats& stats);
lpx::Stream readModel(const std::string& path);
EncoderOptions variant(const std::string& name);
}
