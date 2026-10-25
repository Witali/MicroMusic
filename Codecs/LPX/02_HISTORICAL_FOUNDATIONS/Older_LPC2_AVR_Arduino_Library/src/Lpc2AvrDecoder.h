#pragma once

#include <Arduino.h>
#include <Stream.h>

/*
 * Потоковый декодер экспериментального формата LPC2 из Audio Codec Lab v11.
 *
 * Целевая платформа:
 *   - ATmega328P, 16 МГц (Arduino Uno/Nano)
 *   - 8 кГц рекомендуется
 *   - PWM: OC2B, Arduino D3, несущая 62,5 кГц
 *   - аудиотаймер: Timer1
 *
 * Формат файла:
 *   magic "LPC2", version 1, заголовок 36 байт, затем LSB-first битовый поток.
 *
 * Важно:
 *   Timer1, Timer2, tone(), Servo и analogWrite() на D3/D11 одновременно
 *   использовать нельзя.
 */

#ifndef LPC2_MAX_SAMPLE_RATE
#define LPC2_MAX_SAMPLE_RATE 10000U
#endif

#ifndef LPC2_PWM_OUTPUT_SHIFT
// Внутренний формат Q11: значение 1.0 = 2048.
// Сдвиг 5 даёт около 6 дБ запаса до клиппинга PWM.
#define LPC2_PWM_OUTPUT_SHIFT 5
#endif

class Lpc2AvrDecoder {
public:
  enum Error : uint8_t {
    OK = 0,
    SOURCE_READ_FAILED,
    BAD_MAGIC,
    UNSUPPORTED_VERSION,
    UNSUPPORTED_ORDER,
    BAD_HEADER,
    SAMPLE_RATE_TOO_HIGH,
    TRUNCATED_BITSTREAM,
    BAD_REPEAT,
    TIMER_RANGE_ERROR
  };

  Lpc2AvrDecoder();

  // source должен оставаться открытым всё время воспроизведения.
  bool begin(Stream& source);
  void end();

  // Вызывать как можно чаще в loop(). Здесь читается файл и готовится следующий кадр.
  void service();

  bool isPlaying() const { return playing_; }
  bool isFinished() const { return finished_; }
  bool hasError() const { return error_ != OK; }
  Error errorCode() const { return error_; }
  uint32_t underrunCount() const;

  uint16_t sampleRate() const { return sampleRate_; }
  uint16_t frameSamples() const { return frameSamples_; }
  uint32_t frameCount() const { return frameCount_; }
  uint32_t totalSamples() const { return totalSamples_; }

  // Лёгкая декодерская коррекция, не содержащаяся в файле.
  // Можно задавать до begin() или во время воспроизведения.
  void setBrightnessDb(float db);     // обычно 0...6 дБ, по умолчанию 4 дБ
  void setHighpassHz(uint16_t hz);    // обычно 50...100 Гц, по умолчанию 70 Гц

  // Вызывается ISR Timer1. Публичен только для обработчика прерывания библиотеки.
  uint8_t renderSampleISR();

  static Lpc2AvrDecoder* activeInstance() { return activeInstance_; }

private:
  static const uint8_t ORDER = 10;
  static const uint8_t SUBFRAMES = 8;
  static const uint8_t CHIRP_LENGTH = 15;

  struct RawFrame {
    uint8_t energy;
    uint8_t mode;       // 0 noise, 1 mixed, 2 voiced, 3 transient
    uint8_t pitch;
    bool repeat;
    uint8_t q[ORDER];
    uint8_t qCount;
  };

  struct TargetFrame {
    int16_t aQ11[ORDER];
    uint16_t gainQ15;
    uint16_t periodQ8;
    uint16_t pulseScaleQ11;
    uint8_t mode;
  };

  struct RenderFrame {
    int16_t aStartQ11[ORDER];
    int16_t aStepQ11[ORDER];
    uint16_t gainStartQ15;
    int16_t gainStepQ15;
    uint16_t periodStartQ8;
    int16_t periodStepQ8;
    uint16_t pulseStartQ11;
    int16_t pulseStepQ11;
    uint16_t subEnd[SUBFRAMES];
    uint16_t samples;
    uint8_t previousMode;
    uint8_t currentMode;
    bool last;
  };

  Stream* source_;
  Error error_;

  uint16_t sampleRate_;
  uint16_t frameSamples_;
  uint16_t analysisWindow_;
  uint32_t frameCount_;
  uint32_t totalSamples_;
  uint32_t payloadBits_;
  float preemphasis_;
  float voicingThreshold_;

  uint32_t nextFrameIndex_;
  uint32_t bitsRead_;
  uint8_t bitByte_;
  uint8_t bitPosition_;

  RawFrame previousRaw_;
  bool havePreviousRaw_;
  TargetFrame lastPreparedTarget_;
  bool haveLastPreparedTarget_;

  RenderFrame render_[2];
  volatile uint8_t activeRender_;
  volatile bool queuedReady_;
  volatile bool needFill_;
  volatile bool playing_;
  volatile bool finished_;
  volatile uint32_t underruns_;

  uint16_t sampleInFrame_;
  uint8_t subframe_;
  int16_t activeAQ11_[ORDER];
  int32_t activeGainQ15_;
  int32_t activePeriodQ8_;
  int32_t activePulseScaleQ11_;

  int16_t synthesisHistoryQ11_[ORDER];
  int16_t deemphasisStateQ11_;
  int16_t tiltPreviousQ11_;
  int16_t highpassPreviousXQ11_;
  int32_t highpassPreviousYQ11_;
  int16_t noisePreviousQ11_;

  int32_t pitchCounterQ8_;
  uint8_t chirpIndex_;
  uint32_t rngState_;
  uint8_t lastExcitationMode_;

  int16_t preemphasisQ15_;
  volatile int16_t brightnessBetaQ15_;
  volatile int16_t highpassRQ15_;
  float brightnessDb_;
  uint16_t highpassHz_;

  static Lpc2AvrDecoder* activeInstance_;

  bool readHeader();
  bool readRawByte(uint8_t& value);
  bool readBits(uint8_t count, uint16_t& value);
  bool readFrame(RawFrame& frame);
  bool rawToTarget(const RawFrame& raw, TargetFrame& target);
  void buildRenderFrame(const TargetFrame& previous,
                        const TargetFrame& current,
                        uint32_t frameIndex,
                        RenderFrame& output);
  void activateRenderISR(const RenderFrame& frame);
  void advanceSubframeISR(const RenderFrame& frame);

  void decodeLsf(const RawFrame& raw, float* lsf, uint8_t order);
  void stabilizeLsf(float* lsf, uint8_t order);
  void lsfToLpc(const float* lsf, uint8_t order, float* a);
  float cosPiApprox(float normalized);
  uint16_t pitchPeriodQ8(uint8_t pitchCode) const;
  uint16_t pulseScaleQ11(uint16_t periodQ8) const;

  bool configureTimers();
  void disableTimers();
  void updateOutputFilters();

  static int16_t clamp16(int32_t value, int16_t lo, int16_t hi);
};
