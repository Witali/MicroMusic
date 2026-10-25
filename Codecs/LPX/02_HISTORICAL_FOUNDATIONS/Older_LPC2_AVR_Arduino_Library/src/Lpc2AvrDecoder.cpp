#include "Lpc2AvrDecoder.h"

#include <math.h>
#include <string.h>
#include <avr/pgmspace.h>
#include <util/atomic.h>

#ifdef __AVR__
#include <avr/interrupt.h>
#endif

static const int16_t kCosPiQ15[257] PROGMEM = {
  32767, 32765, 32757, 32745, 32728, 32705, 32678, 32646, 32609, 32567, 32521, 32469,
  32412, 32351, 32285, 32213, 32137, 32057, 31971, 31880, 31785, 31685, 31580, 31470,
  31356, 31237, 31113, 30985, 30852, 30714, 30571, 30424, 30273, 30117, 29956, 29791,
  29621, 29447, 29268, 29085, 28898, 28706, 28510, 28310, 28105, 27896, 27683, 27466,
  27245, 27019, 26790, 26556, 26319, 26077, 25832, 25582, 25329, 25072, 24811, 24547,
  24279, 24007, 23731, 23452, 23170, 22884, 22594, 22301, 22005, 21705, 21403, 21096,
  20787, 20475, 20159, 19841, 19519, 19195, 18868, 18537, 18204, 17869, 17530, 17189,
  16846, 16499, 16151, 15800, 15446, 15090, 14732, 14372, 14010, 13645, 13279, 12910,
  12539, 12167, 11793, 11417, 11039, 10659, 10278, 9896, 9512, 9126, 8739, 8351,
  7962, 7571, 7179, 6786, 6393, 5998, 5602, 5205, 4808, 4410, 4011, 3612,
  3212, 2811, 2410, 2009, 1608, 1206, 804, 402, 0, -402, -804, -1206,
  -1608, -2009, -2410, -2811, -3212, -3612, -4011, -4410, -4808, -5205, -5602, -5998,
  -6393, -6786, -7179, -7571, -7962, -8351, -8739, -9126, -9512, -9896, -10278, -10659,
  -11039, -11417, -11793, -12167, -12539, -12910, -13279, -13645, -14010, -14372, -14732, -15090,
  -15446, -15800, -16151, -16499, -16846, -17189, -17530, -17869, -18204, -18537, -18868, -19195,
  -19519, -19841, -20159, -20475, -20787, -21096, -21403, -21705, -22005, -22301, -22594, -22884,
  -23170, -23452, -23731, -24007, -24279, -24547, -24811, -25072, -25329, -25582, -25832, -26077,
  -26319, -26556, -26790, -27019, -27245, -27466, -27683, -27896, -28105, -28310, -28510, -28706,
  -28898, -29085, -29268, -29447, -29621, -29791, -29956, -30117, -30273, -30424, -30571, -30714,
  -30852, -30985, -31113, -31237, -31356, -31470, -31580, -31685, -31785, -31880, -31971, -32057,
  -32137, -32213, -32285, -32351, -32412, -32469, -32521, -32567, -32609, -32646, -32678, -32705,
  -32728, -32745, -32757, -32765, -32767
};

static const uint16_t kGainQ15[32] PROGMEM = {
  0, 33, 41, 52, 65, 82, 104, 130, 164, 207, 260, 328, 413, 519, 654, 823,
  1036, 1304, 1642, 2067, 2603, 3277, 4125, 5193, 6538, 8231, 10362, 13045, 16422, 20675, 26028, 32767
};

// Частоты pitch-кодов в Гц * 16. Таблица не зависит от частоты дискретизации.
static const uint16_t kPitchFrequencyX16[64] PROGMEM = {
  880, 909, 939, 969, 1001, 1034, 1068, 1103, 1139, 1177, 1215, 1255,
  1296, 1339, 1383, 1428, 1475, 1523, 1573, 1625, 1678, 1733, 1790, 1848,
  1909, 1972, 2036, 2103, 2172, 2243, 2317, 2393, 2471, 2552, 2636, 2723,
  2812, 2904, 2999, 3098, 3199, 3304, 3413, 3524, 3640, 3759, 3883, 4010,
  4142, 4277, 4418, 4562, 4712, 4867, 5026, 5191, 5361, 5537, 5719, 5906,
  6100, 6300, 6507, 6720
};

static const int16_t kChirpQ15[15] PROGMEM = {
  7913, 7913, 7913, 7913, -9044, -9044, -9044, 7913, -9044, -9044, 7913, 7913, -9044, 7913, -9044
};

static const uint8_t kLsfBits10[10] PROGMEM = {5,5,4,4,4,4,4,3,3,3};
static const uint8_t kLsfBits4[4] PROGMEM = {5,5,4,4};

Lpc2AvrDecoder* Lpc2AvrDecoder::activeInstance_ = nullptr;

#ifdef __AVR__
ISR(TIMER1_COMPA_vect) {
  Lpc2AvrDecoder* decoder = Lpc2AvrDecoder::activeInstance();
  OCR2B = decoder ? decoder->renderSampleISR() : 128;
}
#endif

Lpc2AvrDecoder::Lpc2AvrDecoder()
    : source_(nullptr),
      error_(OK),
      sampleRate_(0),
      frameSamples_(0),
      analysisWindow_(0),
      frameCount_(0),
      totalSamples_(0),
      payloadBits_(0),
      preemphasis_(0.0f),
      voicingThreshold_(0.0f),
      nextFrameIndex_(0),
      bitsRead_(0),
      bitByte_(0),
      bitPosition_(8),
      havePreviousRaw_(false),
      haveLastPreparedTarget_(false),
      activeRender_(0),
      queuedReady_(false),
      needFill_(false),
      playing_(false),
      finished_(false),
      underruns_(0),
      sampleInFrame_(0),
      subframe_(0),
      activeGainQ15_(0),
      activePeriodQ8_(0),
      activePulseScaleQ11_(0),
      deemphasisStateQ11_(0),
      tiltPreviousQ11_(0),
      highpassPreviousXQ11_(0),
      highpassPreviousYQ11_(0),
      noisePreviousQ11_(0),
      pitchCounterQ8_(0),
      chirpIndex_(CHIRP_LENGTH),
      rngState_(0x51F15E3DUL),
      lastExcitationMode_(0),
      preemphasisQ15_(0),
      brightnessBetaQ15_(0),
      highpassRQ15_(32700),
      brightnessDb_(4.0f),
      highpassHz_(70) {
  memset(&previousRaw_, 0, sizeof(previousRaw_));
  memset(&lastPreparedTarget_, 0, sizeof(lastPreparedTarget_));
  memset(render_, 0, sizeof(render_));
  memset(activeAQ11_, 0, sizeof(activeAQ11_));
  memset(synthesisHistoryQ11_, 0, sizeof(synthesisHistoryQ11_));
}

int16_t Lpc2AvrDecoder::clamp16(int32_t value, int16_t lo, int16_t hi) {
  if (value < lo) return lo;
  if (value > hi) return hi;
  return (int16_t)value;
}


uint32_t Lpc2AvrDecoder::underrunCount() const {
  uint32_t value;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    value = underruns_;
  }
  return value;
}

void Lpc2AvrDecoder::setBrightnessDb(float db) {
  if (db < 0.0f) db = 0.0f;
  if (db > 9.0f) db = 9.0f;
  brightnessDb_ = db;
  updateOutputFilters();
}

void Lpc2AvrDecoder::setHighpassHz(uint16_t hz) {
  if (hz < 1) hz = 1;
  if (hz > 300) hz = 300;
  highpassHz_ = hz;
  updateOutputFilters();
}

void Lpc2AvrDecoder::updateOutputFilters() {
  if (!sampleRate_) return;

  const float ratio = powf(10.0f, brightnessDb_ / 20.0f);
  const float beta = (ratio - 1.0f) / (ratio + 1.0f);
  const float r = expf(-2.0f * 3.14159265359f * highpassHz_ / sampleRate_);

  const int16_t betaQ15 = clamp16((int32_t)lroundf(beta * 32768.0f), 0, 32700);
  const int16_t rQ15 = clamp16((int32_t)lroundf(r * 32768.0f), 0, 32767);

  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    brightnessBetaQ15_ = betaQ15;
    highpassRQ15_ = rQ15;
  }
}

bool Lpc2AvrDecoder::readRawByte(uint8_t& value) {
  if (!source_) {
    error_ = SOURCE_READ_FAILED;
    return false;
  }
  const int c = source_->read();
  if (c < 0) {
    error_ = SOURCE_READ_FAILED;
    return false;
  }
  value = (uint8_t)c;
  return true;
}

static uint16_t readLe16(const uint8_t* p) {
  return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

static uint32_t readLe32(const uint8_t* p) {
  return (uint32_t)p[0] |
         ((uint32_t)p[1] << 8) |
         ((uint32_t)p[2] << 16) |
         ((uint32_t)p[3] << 24);
}

static float readLeFloat(const uint8_t* p) {
  union {
    uint32_t u;
    float f;
  } value;
  value.u = readLe32(p);
  return value.f;
}

bool Lpc2AvrDecoder::readHeader() {
  uint8_t h[36];
  for (uint8_t i = 0; i < sizeof(h); ++i) {
    if (!readRawByte(h[i])) return false;
  }

  if (h[0] != 'L' || h[1] != 'P' || h[2] != 'C' || h[3] != '2') {
    error_ = BAD_MAGIC;
    return false;
  }
  if (h[4] != 1) {
    error_ = UNSUPPORTED_VERSION;
    return false;
  }
  if (h[5] != ORDER) {
    error_ = UNSUPPORTED_ORDER;
    return false;
  }

  sampleRate_ = readLe16(h + 6);
  frameSamples_ = readLe16(h + 8);
  analysisWindow_ = readLe16(h + 10);
  frameCount_ = readLe32(h + 12);
  totalSamples_ = readLe32(h + 16);
  payloadBits_ = readLe32(h + 20);
  preemphasis_ = readLeFloat(h + 24);
  voicingThreshold_ = readLeFloat(h + 28);

  if (sampleRate_ < 4000 || !frameSamples_ || frameSamples_ < SUBFRAMES ||
      !frameCount_ || !totalSamples_ || preemphasis_ < 0.0f ||
      preemphasis_ > 0.99f) {
    error_ = BAD_HEADER;
    return false;
  }
  if (sampleRate_ > LPC2_MAX_SAMPLE_RATE) {
    error_ = SAMPLE_RATE_TOO_HIGH;
    return false;
  }

  preemphasisQ15_ =
      clamp16((int32_t)lroundf(preemphasis_ * 32768.0f), 0, 32440);
  bitsRead_ = 0;
  bitPosition_ = 8;
  updateOutputFilters();
  return true;
}

bool Lpc2AvrDecoder::readBits(uint8_t count, uint16_t& value) {
  if ((uint32_t)count > payloadBits_ - bitsRead_) {
    error_ = TRUNCATED_BITSTREAM;
    return false;
  }

  value = 0;
  for (uint8_t i = 0; i < count; ++i) {
    if (bitPosition_ >= 8) {
      if (!readRawByte(bitByte_)) {
        error_ = TRUNCATED_BITSTREAM;
        return false;
      }
      bitPosition_ = 0;
    }
    value |= ((uint16_t)((bitByte_ >> bitPosition_) & 1U)) << i;
    ++bitPosition_;
    ++bitsRead_;
  }
  return true;
}

bool Lpc2AvrDecoder::readFrame(RawFrame& frame) {
  memset(&frame, 0, sizeof(frame));
  uint16_t value = 0;

  if (!readBits(5, value)) return false;
  frame.energy = (uint8_t)value;

  if (!frame.energy) {
    frame.mode = 0;
    frame.pitch = 0;
    frame.repeat = false;
    frame.qCount = 0;
    previousRaw_ = frame;
    havePreviousRaw_ = true;
    return true;
  }

  if (!readBits(2, value)) return false;
  frame.mode = (uint8_t)value;
  if (!readBits(1, value)) return false;
  frame.repeat = value != 0;

  const bool voicedClass = frame.mode == 1 || frame.mode == 2;
  if (voicedClass) {
    if (!readBits(6, value)) return false;
    frame.pitch = (uint8_t)value;
    frame.qCount = 10;
  } else {
    frame.pitch = 0;
    frame.qCount = 4;
  }

  if (frame.repeat) {
    const bool previousVoiced =
        havePreviousRaw_ &&
        (previousRaw_.mode == 1 || previousRaw_.mode == 2);
    if (!havePreviousRaw_ || !previousRaw_.energy ||
        previousVoiced != voicedClass ||
        previousRaw_.qCount != frame.qCount) {
      error_ = BAD_REPEAT;
      return false;
    }
    memcpy(frame.q, previousRaw_.q, frame.qCount);
  } else {
    for (uint8_t i = 0; i < frame.qCount; ++i) {
      const uint8_t bits = pgm_read_byte(
          voicedClass ? &kLsfBits10[i] : &kLsfBits4[i]);
      if (!readBits(bits, value)) return false;
      frame.q[i] = (uint8_t)value;
    }
  }

  previousRaw_ = frame;
  havePreviousRaw_ = true;
  return true;
}

void Lpc2AvrDecoder::stabilizeLsf(float* lsf, uint8_t order) {
  for (uint8_t i = 1; i < order; ++i) {
    const float value = lsf[i];
    int16_t j = (int16_t)i - 1;
    while (j >= 0 && lsf[j] > value) {
      lsf[j + 1] = lsf[j];
      --j;
    }
    lsf[j + 1] = value;
  }

  const float separation = order == 10 ? 0.012f : 0.025f;
  const float lo = separation;
  const float hi = 1.0f - separation;

  for (uint8_t i = 0; i < order; ++i) {
    if (lsf[i] < lo) lsf[i] = lo;
    if (lsf[i] > hi) lsf[i] = hi;
  }
  for (uint8_t i = 1; i < order; ++i) {
    const float minimum = lsf[i - 1] + separation;
    if (lsf[i] < minimum) lsf[i] = minimum;
  }
  if (lsf[order - 1] > hi) {
    lsf[order - 1] = hi;
    for (int16_t i = (int16_t)order - 2; i >= 0; --i) {
      const float maximum = lsf[i + 1] - separation;
      if (lsf[i] > maximum) lsf[i] = maximum;
    }
  }
  if (lsf[0] < lo) {
    lsf[0] = lo;
    for (uint8_t i = 1; i < order; ++i) {
      const float minimum = lsf[i - 1] + separation;
      if (lsf[i] < minimum) lsf[i] = minimum;
    }
  }
}

void Lpc2AvrDecoder::decodeLsf(const RawFrame& raw,
                               float* lsf,
                               uint8_t order) {
  const float separation = order == 10 ? 0.012f : 0.025f;
  const float half = order == 10 ? 0.235f : 0.30f;

  for (uint8_t i = 0; i < order; ++i) {
    const uint8_t bits = pgm_read_byte(
        order == 10 ? &kLsfBits10[i] : &kLsfBits4[i]);
    const uint16_t levels = (uint16_t)(((uint16_t)1U << bits) - (uint16_t)1U);
    const float center = (float)(i + 1) / (float)(order + 1);
    float lo = center - half;
    const float hardLo = (float)(i + 1) * separation;
    if (lo < hardLo) lo = hardLo;

    float hi = center + half;
    const float hardHi = 1.0f - (float)(order - i) * separation;
    if (hi > hardHi) hi = hardHi;

    lsf[i] = lo + ((float)raw.q[i] / (float)levels) * (hi - lo);
  }
  stabilizeLsf(lsf, order);
}

float Lpc2AvrDecoder::cosPiApprox(float normalized) {
  if (normalized <= 0.0f) return 1.0f;
  if (normalized >= 1.0f) return -1.0f;

  const float position = normalized * 256.0f;
  const uint16_t index = (uint16_t)position;
  const float fraction = position - index;
  const int16_t a = (int16_t)pgm_read_word(&kCosPiQ15[index]);
  const int16_t b = (int16_t)pgm_read_word(&kCosPiQ15[index + 1]);
  return (a + (b - a) * fraction) / 32767.0f;
}

void Lpc2AvrDecoder::lsfToLpc(const float* lsf,
                              uint8_t order,
                              float* a) {
  float p[12] = {0};
  float q[12] = {0};
  float temp[12] = {0};
  uint8_t pLength = 2;
  uint8_t qLength = 2;
  p[0] = 1.0f;
  p[1] = 1.0f;
  q[0] = 1.0f;
  q[1] = -1.0f;

  for (uint8_t root = 0; root < order; root += 2) {
    memset(temp, 0, sizeof(temp));
    const float c = -2.0f * cosPiApprox(lsf[root]);
    for (uint8_t i = 0; i < pLength; ++i) {
      temp[i] += p[i];
      temp[i + 1] += p[i] * c;
      temp[i + 2] += p[i];
    }
    pLength += 2;
    memcpy(p, temp, sizeof(p));

    memset(temp, 0, sizeof(temp));
    const float d = -2.0f * cosPiApprox(lsf[root + 1]);
    for (uint8_t i = 0; i < qLength; ++i) {
      temp[i] += q[i];
      temp[i + 1] += q[i] * d;
      temp[i + 2] += q[i];
    }
    qLength += 2;
    memcpy(q, temp, sizeof(q));
  }

  a[0] = 1.0f;
  for (uint8_t i = 1; i <= order; ++i) {
    a[i] = 0.5f * (p[i] + q[i]);
  }
}

uint16_t Lpc2AvrDecoder::pitchPeriodQ8(uint8_t pitchCode) const {
  const uint16_t frequencyX16 =
      pgm_read_word(&kPitchFrequencyX16[pitchCode & 63U]);
  const uint32_t numerator = (uint32_t)sampleRate_ * 4096UL;
  return (uint16_t)((numerator + frequencyX16 / 2U) / frequencyX16);
}

uint16_t Lpc2AvrDecoder::pulseScaleQ11(uint16_t periodQ8) const {
  const float period = periodQ8 / 256.0f;
  const float scale = sqrtf(period) * 2048.0f;
  if (scale >= 32767.0f) return 32767;
  return (uint16_t)lroundf(scale);
}

bool Lpc2AvrDecoder::rawToTarget(const RawFrame& raw,
                                 TargetFrame& target) {
  memset(&target, 0, sizeof(target));
  target.mode = raw.mode;
  target.gainQ15 = pgm_read_word(&kGainQ15[raw.energy & 31U]);

  if (haveLastPreparedTarget_) {
    target.periodQ8 = lastPreparedTarget_.periodQ8;
  } else {
    target.periodQ8 = (uint16_t)(((uint32_t)sampleRate_ * 256UL) / 120UL);
  }

  if (raw.mode == 1 || raw.mode == 2) {
    target.periodQ8 = pitchPeriodQ8(raw.pitch);
  }
  target.pulseScaleQ11 = pulseScaleQ11(target.periodQ8);

  if (!raw.energy) {
    target.mode = 0;
    target.gainQ15 = 0;
    memset(target.aQ11, 0, sizeof(target.aQ11));
    return true;
  }

  const uint8_t order = (raw.mode == 1 || raw.mode == 2) ? 10 : 4;
  float lsf[10] = {0};
  float a[11] = {0};
  decodeLsf(raw, lsf, order);
  lsfToLpc(lsf, order, a);

  for (uint8_t i = 0; i < ORDER; ++i) {
    if (i < order) {
      const int32_t value = (int32_t)lroundf(a[i + 1] * 2048.0f);
      target.aQ11[i] = clamp16(value, -32760, 32760);
    } else {
      target.aQ11[i] = 0;
    }
  }
  return true;
}

void Lpc2AvrDecoder::buildRenderFrame(const TargetFrame& previous,
                                      const TargetFrame& current,
                                      uint32_t frameIndex,
                                      RenderFrame& output) {
  memset(&output, 0, sizeof(output));

  const uint32_t startSample = frameIndex * (uint32_t)frameSamples_;
  uint32_t remaining = totalSamples_ > startSample ?
      totalSamples_ - startSample : 0;
  if (remaining > frameSamples_) remaining = frameSamples_;
  output.samples = (uint16_t)remaining;
  output.last = frameIndex + 1 >= frameCount_;
  output.previousMode = previous.mode;
  output.currentMode = current.mode;

  for (uint8_t i = 0; i < ORDER; ++i) {
    const int32_t delta =
        (int32_t)current.aQ11[i] - previous.aQ11[i];
    output.aStartQ11[i] =
        clamp16(previous.aQ11[i] + delta / 16, -32760, 32760);
    output.aStepQ11[i] =
        clamp16(delta / 8, -32760, 32760);
  }

  const int32_t gainDelta =
      (int32_t)current.gainQ15 - previous.gainQ15;
  output.gainStartQ15 =
      (uint16_t)clamp16(previous.gainQ15 + gainDelta / 16, 0, 32767);
  output.gainStepQ15 =
      clamp16(gainDelta / 8, -32767, 32767);

  const int32_t periodDelta =
      (int32_t)current.periodQ8 - previous.periodQ8;
  output.periodStartQ8 =
      (uint16_t)clamp16(previous.periodQ8 + periodDelta / 16, 2 * 256, 32767);
  output.periodStepQ8 =
      clamp16(periodDelta / 8, -32767, 32767);

  const int32_t pulseDelta =
      (int32_t)current.pulseScaleQ11 - previous.pulseScaleQ11;
  output.pulseStartQ11 =
      (uint16_t)clamp16(previous.pulseScaleQ11 + pulseDelta / 16, 0, 32767);
  output.pulseStepQ11 =
      clamp16(pulseDelta / 8, -32767, 32767);

  for (uint8_t i = 0; i < SUBFRAMES; ++i) {
    output.subEnd[i] =
        (uint16_t)(((uint32_t)(i + 1) * output.samples) / SUBFRAMES);
  }
}

void Lpc2AvrDecoder::activateRenderISR(const RenderFrame& frame) {
  sampleInFrame_ = 0;
  subframe_ = 0;
  memcpy(activeAQ11_, frame.aStartQ11, sizeof(activeAQ11_));
  activeGainQ15_ = frame.gainStartQ15;
  activePeriodQ8_ = frame.periodStartQ8;
  activePulseScaleQ11_ = frame.pulseStartQ11;
}

void Lpc2AvrDecoder::advanceSubframeISR(const RenderFrame& frame) {
  if (subframe_ >= SUBFRAMES - 1) return;
  ++subframe_;
  for (uint8_t i = 0; i < ORDER; ++i) {
    activeAQ11_[i] = clamp16(
        (int32_t)activeAQ11_[i] + frame.aStepQ11[i],
        -32760, 32760);
  }
  activeGainQ15_ += frame.gainStepQ15;
  if (activeGainQ15_ < 0) activeGainQ15_ = 0;
  if (activeGainQ15_ > 32767) activeGainQ15_ = 32767;

  activePeriodQ8_ += frame.periodStepQ8;
  if (activePeriodQ8_ < 2 * 256) activePeriodQ8_ = 2 * 256;
  if (activePeriodQ8_ > 32767) activePeriodQ8_ = 32767;

  activePulseScaleQ11_ += frame.pulseStepQ11;
  if (activePulseScaleQ11_ < 0) activePulseScaleQ11_ = 0;
  if (activePulseScaleQ11_ > 32767) activePulseScaleQ11_ = 32767;
}

bool Lpc2AvrDecoder::configureTimers() {
#ifdef __AVR__
  const uint32_t ticks =
      ((uint32_t)F_CPU / 8UL + sampleRate_ / 2U) / sampleRate_;
  if (ticks < 2 || ticks > 65536UL) {
    error_ = TIMER_RANGE_ERROR;
    return false;
  }

  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    // Timer2: Fast PWM, OC2B = Arduino D3, без предделителя.
    pinMode(3, OUTPUT);
    TCCR2A = _BV(COM2B1) | _BV(WGM21) | _BV(WGM20);
    TCCR2B = _BV(CS20);
    OCR2B = 128;

    // Timer1: частота выборок.
    TCCR1A = 0;
    TCCR1B = 0;
    TCNT1 = 0;
    OCR1A = (uint16_t)(ticks - 1UL);
    TCCR1B = _BV(WGM12) | _BV(CS11);
    TIMSK1 |= _BV(OCIE1A);
  }
#endif
  return true;
}

void Lpc2AvrDecoder::disableTimers() {
#ifdef __AVR__
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    TIMSK1 &= (uint8_t)~_BV(OCIE1A);
    OCR2B = 128;
  }
#endif
}

bool Lpc2AvrDecoder::begin(Stream& source) {
  end();
  source_ = &source;
  error_ = OK;
  finished_ = false;
  underruns_ = 0;
  havePreviousRaw_ = false;
  haveLastPreparedTarget_ = false;
  nextFrameIndex_ = 0;
  queuedReady_ = false;
  needFill_ = false;
  activeRender_ = 0;

  memset(synthesisHistoryQ11_, 0, sizeof(synthesisHistoryQ11_));
  deemphasisStateQ11_ = 0;
  tiltPreviousQ11_ = 0;
  highpassPreviousXQ11_ = 0;
  highpassPreviousYQ11_ = 0;
  noisePreviousQ11_ = 0;
  pitchCounterQ8_ = 0;
  chirpIndex_ = CHIRP_LENGTH;
  rngState_ = 0x51F15E3DUL;
  lastExcitationMode_ = 0;

  if (!readHeader()) return false;

  RawFrame raw;
  TargetFrame firstTarget;
  if (!readFrame(raw) || !rawToTarget(raw, firstTarget)) return false;

  buildRenderFrame(firstTarget, firstTarget, 0, render_[0]);
  lastPreparedTarget_ = firstTarget;
  haveLastPreparedTarget_ = true;
  nextFrameIndex_ = 1;

  if (frameCount_ > 1) {
    TargetFrame secondTarget;
    if (!readFrame(raw) || !rawToTarget(raw, secondTarget)) return false;
    buildRenderFrame(lastPreparedTarget_, secondTarget, 1, render_[1]);
    lastPreparedTarget_ = secondTarget;
    nextFrameIndex_ = 2;
    queuedReady_ = true;
  }

  activeRender_ = 0;
  activateRenderISR(render_[0]);

  activeInstance_ = this;
  playing_ = true;
  if (!configureTimers()) {
    playing_ = false;
    activeInstance_ = nullptr;
    return false;
  }
  return true;
}

void Lpc2AvrDecoder::end() {
  disableTimers();
  playing_ = false;
  finished_ = false;
  if (activeInstance_ == this) activeInstance_ = nullptr;
  source_ = nullptr;
}

void Lpc2AvrDecoder::service() {
  if (!playing_ || error_ != OK) return;

  bool fill = false;
  uint8_t inactive = 0;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    if (needFill_) {
      needFill_ = false;
      fill = true;
      inactive = activeRender_ ^ 1U;
    }
  }

  if (!fill) return;
  if (nextFrameIndex_ >= frameCount_) return;

  RawFrame raw;
  TargetFrame target;
  if (!readFrame(raw) || !rawToTarget(raw, target)) {
    playing_ = false;
    disableTimers();
    return;
  }

  buildRenderFrame(lastPreparedTarget_, target,
                   nextFrameIndex_, render_[inactive]);
  lastPreparedTarget_ = target;
  ++nextFrameIndex_;

  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    queuedReady_ = true;
  }
}

uint8_t Lpc2AvrDecoder::renderSampleISR() {
  if (!playing_) return 128;

  RenderFrame& frame = render_[activeRender_];

  if (sampleInFrame_ >= frame.samples) {
    if (frame.last) {
      playing_ = false;
      finished_ = true;
#ifdef __AVR__
      TIMSK1 &= (uint8_t)~_BV(OCIE1A);
#endif
      return 128;
    }

    if (queuedReady_) {
      activeRender_ ^= 1U;
      queuedReady_ = false;
      needFill_ = true;
      activateRenderISR(render_[activeRender_]);
    } else {
      ++underruns_;
      return 128;
    }
  }

  RenderFrame& activeFrame = render_[activeRender_];

  while (subframe_ < SUBFRAMES - 1 &&
         sampleInFrame_ >= activeFrame.subEnd[subframe_]) {
    advanceSubframeISR(activeFrame);
  }

  const uint8_t mode =
      subframe_ < 4 ? activeFrame.previousMode : activeFrame.currentMode;

  if ((lastExcitationMode_ == 0 || lastExcitationMode_ == 3) &&
      (mode == 1 || mode == 2)) {
    pitchCounterQ8_ = 0;
    chirpIndex_ = CHIRP_LENGTH;
  }
  lastExcitationMode_ = mode;

  // xorshift32
  rngState_ ^= rngState_ << 13;
  rngState_ ^= rngState_ >> 17;
  rngState_ ^= rngState_ << 5;

  // Приближение uniform(-1,1)*sqrt(3), Q11.
  const int16_t noiseQ11 =
      (int16_t)((int8_t)(rngState_ >> 24)) * 28;
  const int16_t highNoiseQ11 = clamp16(
      (int32_t)noiseQ11 -
      (((int32_t)26870 * noisePreviousQ11_) >> 15),
      -8192, 8191);
  noisePreviousQ11_ = noiseQ11;

  if (pitchCounterQ8_ <= 0) {
    pitchCounterQ8_ += activePeriodQ8_;
    chirpIndex_ = 0;
  }
  pitchCounterQ8_ -= 256;

  int16_t pulseQ11 = 0;
  if (chirpIndex_ < CHIRP_LENGTH) {
    const int16_t chirp =
        (int16_t)pgm_read_word(&kChirpQ15[chirpIndex_++]);
    pulseQ11 = clamp16(
        ((int32_t)chirp * activePulseScaleQ11_) >> 15,
        -8192, 8191);
  }

  int32_t sourceQ11;
  if (mode == 2) {
    sourceQ11 =
        ((int32_t)241 * pulseQ11 +
         (int32_t)31 * noiseQ11) >> 8;
  } else if (mode == 1) {
    sourceQ11 =
        ((int32_t)148 * pulseQ11 +
         (int32_t)159 * highNoiseQ11) >> 8;
  } else if (mode == 3) {
    const uint16_t boostQ8 =
        256U + (uint16_t)((7U - subframe_) * 205U / 7U);
    sourceQ11 = ((int32_t)highNoiseQ11 * boostQ8) >> 8;
  } else {
    sourceQ11 = noiseQ11;
  }

  int32_t yQ11 =
      (sourceQ11 * activeGainQ15_) >> 15;
  for (uint8_t i = 0; i < ORDER; ++i) {
    yQ11 -=
        ((int32_t)activeAQ11_[i] *
         synthesisHistoryQ11_[i]) >> 11;
  }
  yQ11 = clamp16(yQ11, -16384, 16384);

  for (int8_t i = ORDER - 1; i > 0; --i) {
    synthesisHistoryQ11_[i] = synthesisHistoryQ11_[i - 1];
  }
  synthesisHistoryQ11_[0] = (int16_t)yQ11;

  int32_t dQ11 = yQ11 +
      (((int32_t)preemphasisQ15_ * deemphasisStateQ11_) >> 15);
  dQ11 = clamp16(dQ11, -16384, 16384);
  deemphasisStateQ11_ = (int16_t)dQ11;

  // Лёгкая компенсация спектрального наклона.
  const int16_t beta = brightnessBetaQ15_;
  int32_t brightQ11 = dQ11 -
      (((int32_t)beta * tiltPreviousQ11_) >> 15);
  tiltPreviousQ11_ = (int16_t)dQ11;
  brightQ11 = clamp16(brightQ11, -16384, 16384);

  // DC-block / ФВЧ первого порядка.
  const int16_t hpR = highpassRQ15_;
  int32_t highQ11 =
      brightQ11 - highpassPreviousXQ11_ +
      (((int32_t)hpR * highpassPreviousYQ11_) >> 15);
  highpassPreviousXQ11_ = (int16_t)brightQ11;
  highQ11 = clamp16(highQ11, -16384, 16384);
  highpassPreviousYQ11_ = highQ11;

  ++sampleInFrame_;

  int16_t pwm = (int16_t)(highQ11 >> LPC2_PWM_OUTPUT_SHIFT);
  if (pwm < -127) pwm = -127;
  if (pwm > 127) pwm = 127;
  return (uint8_t)(128 + pwm);
}
