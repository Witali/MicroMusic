MicroMusic PIC16F1503 (ASSEMBLY) — НАЧАТЬ ЗДЕСЬ

1) web/player.html               автономный браузерный эмулятор настоящего PIC HEX
2) firmware/micromusic.asm       главный исходник PIC-ассемблера
3) firmware/micromusic_with_config.hex — программа для PICkit / MPLAB
4) reference/preview_pic16_asm.wav — 14 с музыки, полученной из PIC-инструкций
5) README.md                     полное руководство, ограничения и результаты

Сборка: python tools/build_firmware.py

Внимание: PIC16F1503 16 МГц HFINTOSC; PWM3 RA2; CONFIG1=3FC4,
CONFIG2=3FFF. 62,5 кГц PWM и 12,5 кГц звуковые отсчёты.
Проверено 230 секунд машинной эмуляции, 0 underrun. На железе НЕ проверялось.
