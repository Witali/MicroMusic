#include <Arduino.h>
#include <avr/pgmspace.h>
#include <Lpc2AvrDecoder.h>

// Создайте этот файл командой:
// python3 lp2_to_header.py voice.lp2 voice_lpc2.h voiceLpc2
#include "voice_lpc2.h"

class ProgmemStream : public Stream {
public:
  ProgmemStream(const uint8_t* data, uint32_t length)
      : data_(data), length_(length), position_(0) {}

  int available() override {
    return position_ < length_ ? (int)(length_ - position_) : 0;
  }

  int read() override {
    if (position_ >= length_) return -1;
    return pgm_read_byte(data_ + position_++);
  }

  int peek() override {
    if (position_ >= length_) return -1;
    return pgm_read_byte(data_ + position_);
  }

  void flush() override {}
  size_t write(uint8_t) override { return 0; }

private:
  const uint8_t* data_;
  uint32_t length_;
  uint32_t position_;
};

ProgmemStream audioStream(voiceLpc2, voiceLpc2Length);
Lpc2AvrDecoder decoder;

void setup() {
  decoder.setBrightnessDb(4.0f);
  decoder.setHighpassHz(70);

  if (!decoder.begin(audioStream)) {
    while (true) {}
  }
}

void loop() {
  decoder.service();

  if (decoder.hasError() || decoder.isFinished()) {
    decoder.end();
    while (true) {}
  }
}
