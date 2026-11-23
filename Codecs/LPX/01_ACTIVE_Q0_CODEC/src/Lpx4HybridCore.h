#pragma once
#include <stdint.h>
#include "Lpx4MemoryProfiles.h"
// Host/full-precision synthesis. Select identically in every translation unit.
// The default fixed-point C/ASM decoder and its object layout stay unchanged.
#ifndef LPX4_FLOAT_SYNTHESIS
#define LPX4_FLOAT_SYNTHESIS 0
#endif
#if LPX4_FLOAT_SYNTHESIS != 0 && LPX4_FLOAT_SYNTHESIS != 1
#error LPX4_FLOAT_SYNTHESIS must be 0 or 1
#endif
#if LPX4_FLOAT_SYNTHESIS
#if defined(__AVR__) && !defined(LPX4_ENABLE_PCM16)
#error Floating synthesis on AVR requires LPX4_ENABLE_PCM16=1
#endif
#include <float.h>
#if DBL_MANT_DIG < 53 || DBL_MAX_EXP < 1024 || FLT_RADIX != 2
#error Floating synthesis requires at least IEEE binary64 precision
#else
#include <limits>
#endif
#if defined(LPX4_ENABLE_ASM) && LPX4_ENABLE_ASM
#error Floating synthesis requires C arithmetic: LPX4_ENABLE_ASM=0
#endif
static_assert(DBL_MANT_DIG>=53 && DBL_MAX_EXP>=1024,
              "Floating synthesis requires at least IEEE binary64 precision");
#if DBL_MANT_DIG >= 53 && DBL_MAX_EXP >= 1024 && FLT_RADIX == 2
static_assert(std::numeric_limits<double>::is_iec559,
              "Floating synthesis requires IEEE754 double");
#endif
typedef double Lpx4SynthesisValue;
#else
typedef int16_t Lpx4SynthesisValue;
#endif
// Opt-in sequential input source. Independent of C/ASM arithmetic and table
// storage. Use the same setting for the core and all callers (layout differs).
#ifndef LPX4_ENABLE_INPUT_CALLBACK
#define LPX4_ENABLE_INPUT_CALLBACK 0
#endif
#if LPX4_ENABLE_INPUT_CALLBACK != 0 && LPX4_ENABLE_INPUT_CALLBACK != 1
#error LPX4_ENABLE_INPUT_CALLBACK must be 0 or 1
#endif
#ifndef LPX4_ALLOW_SPARSE
#define LPX4_ALLOW_SPARSE 1
#endif
// Experimental fixed-rate speech v4. Explicit opt-in; v2/v3 stay unchanged.
// Uses the same integer synthesis and C/ASM arithmetic backends.
#ifndef LPX4_ENABLE_SPEECH
#define LPX4_ENABLE_SPEECH 0
#endif
#if LPX4_ENABLE_SPEECH != 0 && LPX4_ENABLE_SPEECH != 1
#error LPX4_ENABLE_SPEECH must be 0 or 1
#endif
#if LPX4_ENABLE_SPEECH && !LPX4_ALLOW_SPARSE
#error Speech v4 requires LPX4_ALLOW_SPARSE
#endif
// Compact speech v5: bounded gap/delta Rice and optional extra innovation.
// Independent opt-in, while sharing the same arithmetic backend selection.
#ifndef LPX4_ENABLE_SPEECH_COMPACT
#define LPX4_ENABLE_SPEECH_COMPACT 0
#endif
#if LPX4_ENABLE_SPEECH_COMPACT != 0 && LPX4_ENABLE_SPEECH_COMPACT != 1
#error LPX4_ENABLE_SPEECH_COMPACT must be 0 or 1
#endif
#if LPX4_ENABLE_SPEECH_COMPACT && !LPX4_ENABLE_SPEECH
#error Compact speech requires LPX4_ENABLE_SPEECH
#endif
// Explicit Flash-size profile: accept v5 by default and omit legacy parsers.
// Use the same flags for the core and every consumer (class layout differs).
// Arithmetic and hardware Flash backend selection remain independent.
#ifndef LPX4_COMPACT_ONLY
#define LPX4_COMPACT_ONLY 0
#endif
#if LPX4_COMPACT_ONLY != 0 && LPX4_COMPACT_ONLY != 1
#error LPX4_COMPACT_ONLY must be 0 or 1
#endif
#if LPX4_COMPACT_ONLY && (!LPX4_ENABLE_SPEECH || !LPX4_ENABLE_SPEECH_COMPACT)
#error LPX4_COMPACT_ONLY requires speech and compact speech
#endif
#if LPX4_MEMORY_PROFILE == LPX4_MEMORY_PROFILE_SRAM512 && !LPX4_COMPACT_ONLY
#error The sram512 memory profile requires LPX4_COMPACT_ONLY
#endif
// Optional version8/mode15 sparse80 parser; independent opt-in, no added state.
// Standard version5 flags remain strict. Use the same flag in all consumers.
#ifndef LPX4_ENABLE_SPARSE80
#define LPX4_ENABLE_SPARSE80 0
#endif
#if LPX4_ENABLE_SPARSE80 != 0 && LPX4_ENABLE_SPARSE80 != 1
#error LPX4_ENABLE_SPARSE80 must be 0 or 1
#endif
#if LPX4_ENABLE_SPARSE80 && !LPX4_COMPACT_ONLY
#error LPX4_ENABLE_SPARSE80 requires LPX4_COMPACT_ONLY
#endif
#if LPX4_COMPACT_ONLY
#define LPX4_MAX_PULSES 3
#else
#define LPX4_MAX_PULSES 10
#endif
// Select the compact wire format independently of C/ASM and memory access.
// V9 is an explicit small-reader profile; all recording parameters stay in ROM.
#ifndef LPX4_COMPACT_VERSION
#define LPX4_COMPACT_VERSION 5
#endif
#if LPX4_COMPACT_VERSION != 5 && LPX4_COMPACT_VERSION != 9
#error Select compact LPX version 5 or 9
#endif
#if LPX4_COMPACT_VERSION == 9 && !LPX4_COMPACT_ONLY
#error Version9 requires compact-only decoding
#endif
// Optional V9 bit5 header extension: one whole-file output gain in Q4.12.
// Select zero to retain the legacy reader/layout and reject gain-tagged files.
#ifndef LPX4_ENABLE_FILE_GAIN
#define LPX4_ENABLE_FILE_GAIN (LPX4_COMPACT_VERSION == 9)
#endif
#if LPX4_ENABLE_FILE_GAIN != 0 && LPX4_ENABLE_FILE_GAIN != 1
#error LPX4_ENABLE_FILE_GAIN must be 0 or 1
#endif
#if LPX4_ENABLE_FILE_GAIN && LPX4_COMPACT_VERSION != 9
#error File gain requires the V9 reader
#endif
// Host-only V9 Long header: bit6 selects uint32 sample/payload lengths.
// Explicit opt-in; ordinary V9/AVR layouts and the bounded begin API stay intact.
#ifndef LPX4_ENABLE_WIDE_V9
#define LPX4_ENABLE_WIDE_V9 0
#endif
#if LPX4_ENABLE_WIDE_V9 != 0 && LPX4_ENABLE_WIDE_V9 != 1
#error LPX4_ENABLE_WIDE_V9 must be 0 or 1
#endif
#if LPX4_ENABLE_WIDE_V9 && (LPX4_COMPACT_VERSION != 9 || !LPX4_COMPACT_ONLY || defined(__AVR__) || LPX4_MEMORY_PROFILE != LPX4_MEMORY_PROFILE_STANDARD)
#error V9 Long requires a non-AVR compact V9 standard-memory build
#endif
#if LPX4_ENABLE_WIDE_V9
typedef uint32_t Lpx4InputSize;
#else
typedef uint16_t Lpx4InputSize;
#endif
// V9 includes all three runtime profiles. The legacy flag only enables the
// long-header version8 reader in a version5 build; it does not select DSP.
#define LPX4_HAS_SPARSE80 (LPX4_COMPACT_VERSION == 9 || LPX4_ENABLE_SPARSE80)
// Mirrored LPC history avoids per-sample shifts, spending 20 B RAM.
// The compact size profile defaults to linear; explicit 1 restores mirroring.
// Both histories retain identical output with C and explicit supported ASM.
#ifndef LPX4_LPC_RING
#define LPX4_LPC_RING (!LPX4_COMPACT_ONLY)
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

// V9 keeps its nominal sampling rate in the stream. Arithmetic is per sample
// and remains identical; legacy formats retain their existing 8 kHz contract.
// Zero is an explicit compatibility/control build, not a different wire format.
#ifndef LPX4_EXTENDED_SAMPLE_RATES
#define LPX4_EXTENDED_SAMPLE_RATES 1
#endif
#if LPX4_EXTENDED_SAMPLE_RATES != 0 && LPX4_EXTENDED_SAMPLE_RATES != 1
#error LPX4_EXTENDED_SAMPLE_RATES must be 0 or 1
#endif
// AVR firmware selects one rate for the whole build; hosts retain a
// rate-agnostic reader. The stream must still declare the selected rate.
#ifndef LPX4_SAMPLE_RATE
#if defined(__AVR__)
#define LPX4_SAMPLE_RATE 8000
#else
#define LPX4_SAMPLE_RATE 0
#endif
#endif
#if LPX4_SAMPLE_RATE != 0 && LPX4_SAMPLE_RATE != 8000 && LPX4_SAMPLE_RATE != 12000 && LPX4_SAMPLE_RATE != 16000
#error LPX4_SAMPLE_RATE must be 0, 8000, 12000 or 16000
#endif
#if LPX4_SAMPLE_RATE > 8000 && (LPX4_COMPACT_VERSION != 9 || !LPX4_EXTENDED_SAMPLE_RATES)
#error Higher sample rates require LPX v9 and extended-rate decoding
#endif

// Advance the ROM pointer and decrement its remaining byte count.
// Zero retains base+cursor+size; hardware Flash access is unchanged.
#ifndef LPX4_ROM_POINTER
#define LPX4_ROM_POINTER 1
#endif
#if LPX4_ROM_POINTER != 0 && LPX4_ROM_POINTER != 1
#error LPX4_ROM_POINTER must be 0 or 1
#endif

// Use the AVR25 layout for universal v9 Flash input. Both arithmetic
// backends share the layout so it stays independent of ASM selection.
#if LPX4_COMPACT_VERSION == 9 && LPX4_ROM_POINTER && !LPX4_ENABLE_INPUT_CALLBACK && \
    defined(__AVR__) && defined(__AVR_ARCH__) && __AVR_ARCH__ == 25 && \
    !defined(LPX3_COST_INSTRUMENT) && !defined(LPX4_FIXED_SPEECH_FLAGS) && \
    !defined(LPX4_FIXED_PRE_Q14) && !defined(LPX4_FIXED_BRIGHT_Q14)
#define LPX4_AVR25_V9_ROM_LAYOUT 1
#else
#define LPX4_AVR25_V9_ROM_LAYOUT 0
#endif

// Compact v9 word layout matches the ten-byte Flash header suffix.
#if LPX4_AVR25_V9_ROM_LAYOUT || (LPX4_COMPACT_VERSION==9 && LPX4_ROM_POINTER && \
    !LPX4_ENABLE_INPUT_CALLBACK && defined(__AVR__) && defined(__AVR_ARCH__) && __AVR_ARCH__==5 && \
    !defined(LPX3_COST_INSTRUMENT) && !defined(LPX4_FIXED_SPEECH_FLAGS) && \
    !defined(LPX4_FIXED_PRE_Q14) && !defined(LPX4_FIXED_BRIGHT_Q14))
#define LPX4_V9_ROM_HEADER_LAYOUT 1
#else
#define LPX4_V9_ROM_HEADER_LAYOUT 0
#endif

// The fixed-register ROM player owns one decoder. Its static pitch history
// uses an aligned SRAM page independently of the arithmetic backend.
#if LPX4_MEMORY_PROFILE == LPX4_MEMORY_PROFILE_SRAM512 && \
    defined(LPX25_ISR_FIXED_REGS) && LPX25_ISR_FIXED_REGS && \
    ((defined(__AVR_ATtiny88__) && LPX4_AVR25_V9_ROM_LAYOUT) || \
     ((defined(__AVR_ATmega328__) || defined(__AVR_ATmega328P__)) && \
      LPX4_COMPACT_VERSION == 9 && LPX4_ROM_POINTER && !LPX4_ENABLE_INPUT_CALLBACK && \
      !defined(LPX3_COST_INSTRUMENT) && !defined(LPX4_FIXED_SPEECH_FLAGS) && \
      !defined(LPX4_FIXED_PRE_Q14) && !defined(LPX4_FIXED_BRIGHT_Q14)))
#define LPX4_PLAYER_PITCH_PAGE 1
#else
#define LPX4_PLAYER_PITCH_PAGE 0
#endif

// Rotate the LPC anchor halves without vector copies. The v9 ROM layout
// keeps byte offsets; other builds retain their original word offsets.
// No self-referencing pointers: ordinary value copies of the object stay valid.
#ifndef LPX4_ROTATE_LPC_ANCHORS
#define LPX4_ROTATE_LPC_ANCHORS 1
#endif
#if LPX4_ROTATE_LPC_ANCHORS != 0 && LPX4_ROTATE_LPC_ANCHORS != 1
#error LPX4_ROTATE_LPC_ANCHORS must be0 or1
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

// While reading a new LPC2 spectrum, the upper anchor is dead until
// midpoint output replaces it. Both arithmetic backends share this layout.
#define LPX4_LPC2_LSF_OVERLAY (LPX4_PLAYER_PITCH_PAGE && LPX4_V9_ROM_HEADER_LAYOUT && \
    LPX4_COMPACT_ONLY && LPX3_LPC_SEGMENTS==2 && LPX4_ROTATE_LPC_ANCHORS && !LPX4_FLOAT_SYNTHESIS)

// A complete dynamic half visits both anchors and returns to anchor zero.
// Tiny88 derives that phase directly. AVR5 retains its existing phase byte.
#define LPX4_TINY_ANCHOR_PHASE (LPX4_LPC2_LSF_OVERLAY && LPX4_AVR25_V9_ROM_LAYOUT)


// Optional local O2 tuning; arithmetic/Flash backend selection is separate.
#ifndef LPX4_FUNCTION_TUNING
#define LPX4_FUNCTION_TUNING 7
#endif
#if LPX4_FUNCTION_TUNING < 0 || LPX4_FUNCTION_TUNING > 7
#error LPX4_FUNCTION_TUNING must be 0..7
#endif
#define LPX4_TUNE_SAMPLE
#define LPX4_TUNE_CODES
#define LPX4_TUNE_READERS
#if defined(__AVR_ARCH__) && __AVR_ARCH__==5 && defined(__GNUC__) && !defined(__clang__)
#if LPX4_FUNCTION_TUNING&1
#undef LPX4_TUNE_SAMPLE
#define LPX4_TUNE_SAMPLE __attribute__((optimize("O2")))
#endif
#if LPX4_FUNCTION_TUNING&2
#undef LPX4_TUNE_CODES
#define LPX4_TUNE_CODES __attribute__((optimize("O2")))
#endif
#if LPX4_FUNCTION_TUNING&4
#undef LPX4_TUNE_READERS
#define LPX4_TUNE_READERS __attribute__((optimize("O2")))
#endif
#endif

// v6/v7: small on-device profile: 10-bit LSF, 80-sample Rice blocks.
// ROM input by default; an explicit callback build also accepts sequential IO.
class Lpx4HybridCore {
public:
    enum Error : uint8_t { NONE=0, BAD_HEADER, UNSUPPORTED, CORRUPT_STREAM, END_OF_ROM };
    Lpx4HybridCore();
#if LPX4_COMPACT_VERSION == 9
    // Keep cold header setup out of the foreground playback stack under LTO.
    __attribute__((noinline))
#endif
    bool begin(const uint8_t* bytesInProgmem, uint16_t size);
#if LPX4_ENABLE_WIDE_V9
    // Accepts standard V9 and the explicitly marked V9 Long extension.
    bool beginWideV9(const uint8_t* input, uint32_t size);
#endif
#if LPX4_ENABLE_INPUT_CALLBACK
    // Return 0..255, or -1 on input failure/EOF. The source must already be
    // positioned at this segment; size bounds all reads, including the header.
    typedef int16_t (*ReadByte)(void* context);
    bool beginStream(ReadByte reader, void* context, uint16_t size);
#endif
    LPX4_TUNE_SAMPLE bool next(uint8_t& pcm);  // legacy 8-bit PWM sample
#if !defined(__AVR__) || defined(LPX4_ENABLE_PCM16)
    bool nextQ14(int16_t& out); // signed Q14 postfilter (no PWM)
    bool nextS16(int16_t& out); // signed PCM16 = saturated(2*Q14)
#endif
#if LPX4_FLOAT_SYNTHESIS
    // Full-precision normalized postfilter signal, clamped to [-1,+1].
    bool nextFloat(double& out);
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
    // Compact metadata stays wide even after invalid begin; subtract low
    // words modulo16 before widening to preserve its zero-progress contract.
    uint32_t produced() const {
#if LPX4_BATCHED_REMAINING
#if LPX4_COMPACT_ONLY && !LPX4_ENABLE_WIDE_V9
        return (uint16_t)((uint16_t)sampleCount_-remaining_)+subPos_;
#else
        return sampleCount_-remaining_+subPos_;
#endif
#else
#if LPX4_COMPACT_ONLY && !LPX4_ENABLE_WIDE_V9
        return (uint16_t)((uint16_t)sampleCount_-remaining_);
#else
        return sampleCount_-remaining_;
#endif
#endif
    }
    uint16_t sampleRate() const {return sampleRate_;}
    uint16_t fileGainQ12() const {
#if LPX4_ENABLE_FILE_GAIN
        return fileGainQ12_;
#else
        return 4096;
#endif
    }
#ifdef LPX3_Q_DIAG
    int8_t debugLastQ() const {return lastQ_;}
#endif
#ifdef LPX3_COST_INSTRUMENT
    uint32_t lsfConverts() const {return lsfConverts_;}
    uint32_t bitCalls() const {return bitCalls_;}
    uint32_t romByteCalls() const {return romByteCalls_;}
#endif
private:
    // Stored after the hot fields/arrays to preserve existing ASM offsets.
    // Declaration is at the class tail below.
    // The ROM player owns a static instance whose storage is zeroed by
    // startup. Keep automatic instances on the normal constructor.
    friend struct Lpx4RomPlayer;
    struct StaticZeroInit {};
    explicit Lpx4HybridCore(StaticZeroInit) {}
#if LPX4_V9_ROM_HEADER_LAYOUT
    // Only the one-shot ROM player may open a stream in zeroed BSS.
    bool beginRom(const uint8_t* input,uint16_t size,bool reset);
#endif

    // Stream lifetime and container/entropy readers.
    // Share one clearing loop between construction and begin(), even with LTO.
    __attribute__((noinline)) void resetState();
#if LPX4_ENABLE_INPUT_CALLBACK
    bool beginSource(Lpx4InputSize size);
#endif
    LPX4_TUNE_READERS uint8_t readByte();
    uint16_t read16();
    uint32_t read32();
    LPX4_TUNE_READERS uint8_t readBits(uint8_t n);
    __attribute__((noinline)) LPX4_TUNE_READERS uint8_t readOne();
#if !LPX4_COMPACT_ONLY
    __attribute__((always_inline)) inline int8_t readHuffman3();
#endif
    bool readFrame();
#if LPX4_ENABLE_SPEECH_COMPACT
    uint8_t readSpeechRice(uint8_t k,uint8_t width);
#endif
#if !LPX4_COMPACT_ONLY
    bool readBlock();
#endif
    bool readSubframe();
    bool prepareSubframe();
    // Excitation reconstruction.
#if LPX4_COMPACT_ONLY && LPX4_COMPACT_VERSION==9 && LPX4_PLAYER_PITCH_PAGE && defined(__AVR_ARCH__) && __AVR_ARCH__==5
    static int32_t decodeCompactAvr5(uint8_t*);
#endif
    int16_t pitchPredict() const;
#if !LPX4_COMPACT_ONLY
    __attribute__((always_inline)) inline bool readUnary8(uint8_t& high);
#endif
    LPX4_TUNE_CODES bool decodeCode(int8_t& q);
#if !defined(__AVR__) || defined(LPX4_ENABLE_PCM16)
    LPX4_TUNE_SAMPLE bool nextCore(Lpx4SynthesisValue& postfilterQ14);
#endif
    // LPC spectrum conversion and interpolation.
    void interpolateLsf(uint8_t sub);
    void convertLsfAt(uint8_t t,Lpx4SynthesisValue* out);
#if LPX4_MEMORY_PROFILE == LPX4_MEMORY_PROFILE_STANDARD && !LPX4_FLOAT_SYNTHESIS
    void polyFactor(int32_t* p,int16_t c,uint8_t n);
#endif
    static int16_t clamp(int32_t n,int16_t low,int16_t high);
    // Keep per-sample state within AVR's short displacement range. Arrays
    // are addressed through pointers; frame-only polynomial workspace follows.
    const uint8_t* data_;
#if LPX4_V9_ROM_HEADER_LAYOUT
    uint16_t sampleRate_,sampleCount_,preQ14_,brightQ14_,bytes_;
    uint16_t remaining_;
#else
    Lpx4InputSize bytes_;
#if !LPX4_ROM_POINTER
    Lpx4InputSize cursor_;
#endif
#if LPX4_COMPACT_VERSION == 9 && !LPX4_ENABLE_WIDE_V9
    // Every serialized v9 count, including rejected values, fits one word.
    // Public metadata remains uint32_t through the existing accessors.
    uint16_t sampleCount_;
#else
    uint32_t sampleCount_;
#endif
#if LPX4_COMPACT_ONLY && !LPX4_ENABLE_WIDE_V9
    uint16_t remaining_;
#else
    uint32_t remaining_;
#endif
    uint16_t sampleRate_;
    // SRAM512 ROM recipes already pin these constants in every translation
    // unit. Validate the header locally instead of retaining unused copies.
#if LPX4_MEMORY_PROFILE != LPX4_MEMORY_PROFILE_SRAM512 || !defined(LPX4_FIXED_PRE_Q14)
    uint16_t preQ14_;
#endif
#if LPX4_MEMORY_PROFILE != LPX4_MEMORY_PROFILE_SRAM512 || !defined(LPX4_FIXED_BRIGHT_Q14)
    uint16_t brightQ14_;
#endif
#endif
    // resetState() clears this scalar/array span through the end of cur_.
    // Keep retained metadata and input ownership outside that span.
    uint16_t blockStep_;
    Lpx4SynthesisValue prevDeemph_;
    uint8_t subPos_,subIndex_; // compact: low3 subframe, bit3 post-readFrame half
#if LPX4_BATCHED_REMAINING
    uint8_t subEnd_;
#endif
#if LPX4_COMPACT_ONLY
    uint8_t bitBuffer_,bitsLeft_,lag_,gain_,ringCursor_;
#else
    uint8_t quantLimit_;
    uint8_t mode_,blockScale_,bitBuffer_,bitsLeft_,riceK_;
    uint8_t subType_,lag_,gain_,ringCursor_;
#endif
#if LPX4_ENABLE_SPEECH
    // Common:profile4/6. Compact-only:validated v5 flags (bit1 profile,bit7 extras).
#if LPX4_MEMORY_PROFILE != LPX4_MEMORY_PROFILE_SRAM512 || !defined(LPX4_FIXED_SPEECH_FLAGS)
    uint8_t speechProfile_;
#endif
#if !LPX4_COMPACT_ONLY
    uint8_t speechHalf_;
#endif
#endif
#if LPX4_ENABLE_SPEECH_COMPACT && !LPX4_COMPACT_ONLY
    uint8_t speechCompact_; // bit0 v5, bit7 optional-extra markers
#endif
#if LPX4_V3_FEATURES && !LPX4_COMPACT_ONLY
    uint8_t formatFeatures_;
#endif
#if LPX4_ALLOW_SPARSE
#if !LPX4_AVR25_V9_ROM_LAYOUT
    uint8_t pulseCount_;
#endif
    uint8_t pulseIndex_;
#endif
    Error error_;
#if LPX4_COMPACT_VERSION == 9
    bool initializedFrame_:1;
    bool lsfCached_:1,staticSpectrum_:1;
#else
    bool initializedFrame_;
    bool lsfCached_,staticSpectrum_;
#endif
#if LPX4_ROTATE_LPC_ANCHORS && !LPX4_TINY_ANCHOR_PHASE
    uint8_t lpcAnchorOffset_;
#endif
    // The AVR5 circular walk needs ten words. Its linear fallback skips
    // storing the oldest word, so it fits the same allocation.
#if defined(__AVR_ARCH__) && __AVR_ARCH__ == 5
    static constexpr bool kShiftHistorySpare=false;
#else
    static constexpr bool kShiftHistorySpare=LPX4_COMPACT_VERSION==9;
#endif
    Lpx4SynthesisValue a_[10],hist_[LPX4_LPC_RING?20:10+kShiftHistorySpare];
#if LPX4_PLAYER_PITCH_PAGE
    static int8_t ringQ_[256];
#else
    int8_t ringQ_[256];
#endif
#if LPX4_ALLOW_SPARSE
    uint8_t pulsePos_[LPX4_MAX_PULSES+LPX4_AVR25_V9_ROM_LAYOUT];
    int8_t pulseAmp_[LPX4_MAX_PULSES];
#endif
#if LPX4_COMPACT_ONLY
#if LPX4_LPC2_LSF_OVERLAY
    uint8_t cur_[10];
#else
    uint8_t prev_[10],cur_[10]; // v5 grid index + 1; zero means untouched
#endif
#else
    int16_t prev_[10],cur_[10];
#endif
#if LPX4_ROTATE_LPC_ANCHORS
    Lpx4SynthesisValue lpcAnchors_[20];
#else
    Lpx4SynthesisValue prevLpc_[10],curLpc_[10];
#endif
#if LPX4_MEMORY_PROFILE == LPX4_MEMORY_PROFILE_STANDARD && !LPX4_FLOAT_SYNTHESIS
    int32_t polyP_[12],polyQ_[12];
#endif
#ifdef LPX3_Q_DIAG
    int8_t lastQ_;
#endif
#ifdef LPX3_COST_INSTRUMENT
    uint32_t lsfConverts_,bitCalls_,romByteCalls_;
#endif
#if LPX4_ENABLE_INPUT_CALLBACK
    // Cold input state stays after the arithmetic workspace: hot AVR offsets
    // and arithmetic backend selection are unchanged.
    ReadByte inputReader_;
    void* inputContext_;
#endif
#if LPX4_ENABLE_FILE_GAIN
    uint16_t fileGainQ12_;
#endif
};

#undef LPX4_TUNE_SAMPLE
#undef LPX4_TUNE_CODES
#undef LPX4_TUNE_READERS
