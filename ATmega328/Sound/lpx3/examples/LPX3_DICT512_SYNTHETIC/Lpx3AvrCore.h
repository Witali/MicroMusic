#pragma once
#include <stdint.h>
// Shared configuration for the Arduino sketch and the .cpp translation unit.
#ifndef LPX3_FAST_LPC_INTERP
#define LPX3_FAST_LPC_INTERP 1
#endif
#ifndef LPX3_LPC_SEGMENTS
#define LPX3_LPC_SEGMENTS 2
#endif
#ifndef LPX3_PAIR_DICT_BYTES
#define LPX3_PAIR_DICT_BYTES 512
#endif
#if LPX3_PAIR_DICT_BYTES && LPX3_PAIR_DICT_BYTES!=64 && LPX3_PAIR_DICT_BYTES!=128 && LPX3_PAIR_DICT_BYTES!=256 && LPX3_PAIR_DICT_BYTES!=512
#error LPX3_PAIR_DICT_BYTES must be 0,64,128,256,512
#endif

/* LPX3-AVR (L3AV) foreground decoder, no malloc and no floating point.
 * ATmega328P targeted, but portable to a desktop compiler for cross-check.
 * Decoder DOES NOT own the timer, ISR or audio buffer.
 * Data is supplied by a random-address ROM reader, e.g. pgm_read_byte_near.
 */
class Lpx3AvrCore {
public:
    // L3AV data must reside within the ATmega328P 32 KiB program address space.
    // 16-bit ROM offsets avoid unnecessary 32-bit operations in the sample loop.
    typedef uint8_t (*ReadByte)(void* context, uint16_t offset);
    enum Error : uint8_t { NONE=0, BAD_HEADER, UNSUPPORTED, CORRUPT_STREAM, END_OF_ROM };
    Lpx3AvrCore();
    bool begin(ReadByte read, void* ctx, uint16_t bytes);
    bool next(uint8_t& sample); // true for each decoded PCM8 sample, false after EOS or error
#ifdef LPX3_COEFF_EXPORT
    void copyCoefficients(int16_t out[10]) const {
        for(uint8_t i=0;i<10;i++)out[i]=a_[i];
    }
#endif
#ifdef LPX3_COST_INSTRUMENT
    uint32_t lsfConverts() const { return lsfConverts_; }
#endif
#ifdef LPX3_Q_DIAG
    int8_t debugLastQ() const { return lastQ_; }
    uint8_t debugMode() const { return mode_; }
    uint8_t debugScale() const { return blockScale_; }
    int16_t debugPred() const { return hist_[0]; }
    int16_t debugDeemph() const { return prevDeemph_; }
#endif
    uint32_t samples() const { return sampleCount_; }
    uint32_t produced() const { return position_; }
    uint16_t sampleRate() const { return sampleRate_; }
    Error error() const { return error_; }
    bool finished() const { return position_==sampleCount_ && !error_; }
private:
    uint8_t readByte();
    uint16_t read16();
    uint32_t read32();
    bool readFrame();
    bool readBlock();
    bool decodeCode(int8_t& v);
    uint8_t rawBit();
    uint8_t huffBit();
    void interpolate(uint8_t sub);
    void interpolateLsf(uint8_t sub);
#ifdef LPX3_FAST_LPC_INTERP
    void convertLsfAt(uint8_t t,int16_t* out);
#endif
    void polyFactor(int32_t* coefficients,int16_t c,uint8_t n);
    static int16_t clamp(int32_t v, int16_t low, int16_t high);
    static int16_t q12(int16_t value, uint8_t scale);
    ReadByte reader_;void* context_;
    uint16_t bytes_, cursor_;
    uint32_t sampleCount_, position_;
    uint16_t sampleRate_, preQ14_, brightQ14_;
    int16_t prev_[10],cur_[10],a_[10],hist_[10];
#ifdef LPX3_FAST_LPC_INTERP
    int16_t prevLpc_[10],curLpc_[10];
    bool lsfCached_;
#endif
    int32_t polyP_[12],polyQ_[12],polyTmp_[12];
    int16_t previousQuant_[10];
    int16_t prevDeemph_,prevBright_;
    uint8_t framePos_,blockPos_,subPos_,subIndex_;
    uint8_t coeffScale_, coeffBits_, isLsf_, mode_,blockScale_,bitBuffer_,bitsLeft_;
    uint8_t containerVersion_, riceMode_, riceK_, pairMode_, pairPending_, pairSecond_;
    uint8_t dictSlotsBits_, dictTiered_;
#if LPX3_PAIR_DICT_BYTES
    int8_t pairDict_[LPX3_PAIR_DICT_BYTES]; // 2 bytes per pair, first byte=127 means uninitialized
#endif
    Error error_;
    bool initializedFrame_;
#ifdef LPX3_Q_DIAG
    int8_t lastQ_;
#endif
#ifdef LPX3_COST_INSTRUMENT
    uint32_t lsfConverts_;
#endif
};
