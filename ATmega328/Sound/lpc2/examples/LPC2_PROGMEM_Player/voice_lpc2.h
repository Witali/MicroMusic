#pragma once
#include <Arduino.h>
#include <avr/pgmspace.h>

// Замените этот файл выводом tools/lp2_to_header.py.
const uint8_t voiceLpc2[] PROGMEM = {
  // Пустой placeholder не является корректным LPC2-файлом.
  0x00
};
const uint32_t voiceLpc2Length = sizeof(voiceLpc2);
