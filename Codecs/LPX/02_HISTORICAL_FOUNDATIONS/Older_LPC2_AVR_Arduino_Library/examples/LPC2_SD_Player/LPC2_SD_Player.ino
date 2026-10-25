#include <SPI.h>
#include <SD.h>
#include <Lpc2AvrDecoder.h>

static const uint8_t SD_CS_PIN = 10;
static const char AUDIO_FILE[] = "VOICE.LP2";

File audioFile;
Lpc2AvrDecoder decoder;

void printDecoderError(Lpc2AvrDecoder::Error error) {
  Serial.print(F("LPC2 error code: "));
  Serial.println((uint8_t)error);
}

void setup() {
  Serial.begin(115200);

  if (!SD.begin(SD_CS_PIN)) {
    Serial.println(F("SD init failed"));
    return;
  }

  audioFile = SD.open(AUDIO_FILE, FILE_READ);
  if (!audioFile) {
    Serial.println(F("VOICE.LP2 not found"));
    return;
  }

  // Эти параметры не увеличивают файл и выполняются только в декодере.
  decoder.setBrightnessDb(4.0f);
  decoder.setHighpassHz(70);

  if (!decoder.begin(audioFile)) {
    printDecoderError(decoder.errorCode());
    audioFile.close();
    return;
  }

  Serial.print(F("LPC2 started, sample rate: "));
  Serial.println(decoder.sampleRate());
}

void loop() {
  // Никаких delay() во время воспроизведения.
  decoder.service();

  if (decoder.hasError()) {
    printDecoderError(decoder.errorCode());
    decoder.end();
    audioFile.close();
    while (true) {}
  }

  if (decoder.isFinished()) {
    Serial.print(F("Finished. Underruns: "));
    Serial.println(decoder.underrunCount());
    decoder.end();
    audioFile.close();
    while (true) {}
  }
}
