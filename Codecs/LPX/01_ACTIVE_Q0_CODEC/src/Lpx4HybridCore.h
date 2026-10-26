#pragma once
#include <stdint.h>
#ifndef LPX4_ALLOW_SPARSE
#define LPX4_ALLOW_SPARSE 1
#endif
#define LPX4_MAX_PULSES 10
// Mirrored LPC history removes per-sample history shifts, spending 20 B RAM.
// Zero retains the smaller linear history with identical output on C/ASM.
#ifndef LPX4_LPC_RING
#define LPX4_LPC_RING 1
#endif
#if LPX4_LPC_RING != 0 && LPX4_LPC_RING != 1
#error LPX4_LPC_RING must be 0 or 1
#endif

// Cache scale*16 per block and feed synthesis an exact Q4 excitation.
// Zero retains the original unscaled input, on C and ASM alike.
#ifndef LPX4_EXCITATION_Q4
#define LPX4_EXCITATION_Q4 1
#endif
#if LPX4_EXCITATION_Q4 != 0 && LPX4_EXCITATION_Q4 != 1
#error LPX4_EXCITATION_Q4 must be 0 or 1
#endif

// Commit the wide remaining count at20-sample boundaries; subPos provides
// exact public progress within the current subframe. Zero keeps old updates.
#ifndef LPX4_BATCHED_REMAINING
#define LPX4_BATCHED_REMAINING 1
#endif
#if LPX4_BATCHED_REMAINING != 0 && LPX4_BATCHED_REMAINING != 1
#error LPX4_BATCHED_REMAINING must be 0 or 1
#endif

// Optional compact-container parser. Zero keeps the original v2-only build.
// 4 scale repeat, 8 width repeat, 16 subheader repeat, 32 zero headers,
// 64 small LSF Rice deltas. The stream may only use compiled feature bits.
#ifndef LPX4_V3_FEATURES
#define LPX4_V3_FEATURES 0
#endif
#if LPX4_V3_FEATURES < 0 || (LPX4_V3_FEATURES & ~124)
#error Unsupported LPX4_V3_FEATURES
#endif
#ifndef LPX3_LPC_SEGMENTS
#define LPX3_LPC_SEGMENTS 2
#endif
// v6/v7: small on-device profile: 10-bit LSF, 80-sample Rice blocks.
// ROM-backed stream only (no callbacks, no LSF8 or legacy Huffman).
class Lpx4HybridCore {
public:
    enum Error : uint8_t { NONE=0, BAD_HEADER, UNSUPPORTED, CORRUPT_STREAM, END_OF_ROM };
    Lpx4HybridCore();
    bool begin(const uint8_t* bytesInProgmem, uint16_t size);
    bool next(uint8_t& pcm);  // legacy 8-bit PWM sample
#if !defined(__AVR__) || defined(LPX4_ENABLE_PCM16)
    bool nextQ14(int16_t& out); // signed Q14 postfilter (no PWM)
    bool nextS16(int16_t& out); // signed PCM16 = saturated(2*Q14)
#endif
    Error error() const {return error_;}
    bool finished() const {
#if LPX4_BATCHED_REMAINING
        return subPos_==subEnd_&&!error_;
#else
        return !remaining_&&!error_;
#endif
    }
    uint32_t samples() const {return sampleCount_;}
    uint32_t produced() const {
#if LPX4_BATCHED_REMAINING
        return sampleCount_-remaining_+subPos_;
#else
        return sampleCount_-remaining_;
#endif
    }
    uint16_t sampleRate() const {return sampleRate_;}
#ifdef LPX3_Q_DIAG
    int8_t debugLastQ() const {return lastQ_;}
#endif
#ifdef LPX3_COST_INSTRUMENT
    uint32_t lsfConverts() const {return lsfConverts_;}
    uint32_t bitCalls() const {return bitCalls_;}
    uint32_t romByteCalls() const {return romByteCalls_;}
#endif
private:
    uint8_t readByte();
    uint16_t read16();
    uint32_t read32();
    uint8_t readBits(uint8_t n);
    __attribute__((noinline)) uint8_t readOne();
    __attribute__((always_inline)) inline int8_t readHuffman3();
    bool readFrame();
    bool readBlock();
    bool readSubframe();
    __attribute__((always_inline)) inline int16_t pitchPredict() const;
    bool decodeCode(int8_t& q);
#if !defined(__AVR__) || defined(LPX4_ENABLE_PCM16)
    bool nextCore(int16_t& postfilterQ14);
#endif
    void interpolate(uint8_t sub);
    void interpolateLsf(uint8_t sub);
    void convertLsfAt(uint8_t t,int16_t* out);
    void polyFactor(int32_t* p,int16_t c,uint8_t n);
    static int16_t clamp(int32_t n,int16_t low,int16_t high);
    // Keep per-sample state within AVR's short displacement range. Arrays
    // are addressed through pointers; frame-only polynomial workspace follows.
    const uint8_t* data_;
    uint16_t bytes_,cursor_;
    uint32_t sampleCount_,remaining_;
    uint16_t sampleRate_,preQ14_,brightQ14_,blockStep_;
    int16_t prevDeemph_,prevBright_;
    uint8_t subPos_,subIndex_;
#if LPX4_BATCHED_REMAINING
    uint8_t subEnd_;
#endif
    uint8_t quantLimit_;
    uint8_t mode_,blockScale_,bitBuffer_,bitsLeft_,riceK_;
    uint8_t subType_,lag_,gain_,ringCursor_;
#if LPX4_V3_FEATURES
    uint8_t formatFeatures_;
#endif
#if LPX4_ALLOW_SPARSE
    uint8_t pulseCount_,pulseIndex_;
#endif
    Error error_;
    bool initializedFrame_;
    bool lsfCached_,staticSpectrum_;
    int16_t a_[10],hist_[LPX4_LPC_RING?20:10];
    int8_t ringQ_[256];
#if LPX4_ALLOW_SPARSE
    uint8_t pulsePos_[LPX4_MAX_PULSES];
    int8_t pulseAmp_[LPX4_MAX_PULSES];
#endif
    int16_t prev_[10],cur_[10];
    int16_t prevLpc_[10],curLpc_[10];
    int32_t polyP_[12],polyQ_[12];
#ifdef LPX3_Q_DIAG
    int8_t lastQ_;
#endif
#ifdef LPX3_COST_INSTRUMENT
    uint32_t lsfConverts_,bitCalls_,romByteCalls_;
#endif
};
