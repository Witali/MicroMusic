// LG1 experimental full-stream decoder. Production LPX formats are unchanged.
#pragma once
#include <stddef.h>
#include <stdint.h>
#include "Lpx4Math.h"

namespace lbg1 {
// Shared integer scale contract. Invalid scale/log inputs return 0 or -1.
uint16_t stepForScale(uint8_t scale);
int16_t logStart(uint8_t scale);
uint16_t logToStep(int16_t log2Q8);

class Decoder {
public:
    typedef bool (*ReadByte)(void* context,uint16_t offset,uint8_t* value);
    enum Error : uint8_t {
        OK=0, BAD_HEADER=1, TRUNCATED=2, READ_FAILURE=3,
        BAD_ANCHOR=4, COEFFICIENT_RANGE=5, BAD_RUN=6,
        BAD_CURVE=7, BAD_PULSE=8, TRAILING_DATA=9
    };
    Decoder();
    bool begin(const uint8_t* data,uint16_t size);
    bool beginCallback(ReadByte reader,void* context,uint16_t size);
    bool next(uint8_t& pwm);
    bool nextS16(int16_t& pcm);
    bool nextQ14(int16_t& q14);
    bool finished() const { return remaining_==0; }
    uint8_t error() const { return error_; }
    uint16_t sampleCount() const { return sampleCount_; }
    uint16_t sampleRate() const { return 8000; }

private:
    // The supported AVR5 circular helper reads this position and the nearby
    // ten-word history. Other targets and explicit C use a linear history.
    uint8_t subPos_;
    int16_t history_[10];
    int16_t base_[10],target_[10],a_[10];
    int8_t excitation_[256];
    const uint8_t* input_;
    ReadByte reader_;
    void* context_;
    uint16_t length_,cursor_,remaining_,sampleCount_;
    // Keep these adjacent for the existing AVR5 paired postfilter helper.
    uint16_t pre_,bright_;
    int16_t previousDeemphasis_;
    uint16_t step_,scaleRun_,pitchRun_;
    int16_t logQ8_,logSlope_;
    uint8_t bitBuffer_,bitsLeft_,profile_,error_,subframe_,ringCursor_;
    uint8_t scaleMode_,pitchMode_,gain_,lag_;
    int8_t pitchSlope_;
    uint8_t pulsePosition_[2],extraPosition_;
    int8_t pulseAmplitude_[2],extraAmplitude_;
    bool firstFrame_,dynamicFrame_;

    void reset();
    bool header();
    bool fail(uint8_t error);
    uint8_t readAt(uint16_t offset);
    uint16_t readWord(uint8_t offset);
    uint16_t bits(uint8_t count);
    int16_t signedBits(uint8_t count);
    uint16_t duration();
    bool anchor();
    bool scale();
    bool pitch();
    void literalPitch();
    bool packet();
    bool prepare();
    bool sample(int16_t& q14);
};
}
