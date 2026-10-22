# Официальные документы, независимые симуляторы и проверяемые утверждения

## Microchip

- [PIC16(L)F1503 Datasheet DS40001607D](https://ww1.microchip.com/downloads/en/DeviceDoc/40001607D.pdf) — Enhanced Mid-Range ISA, RAM, Interrupts, Timer0/1/2, PWM3, FOSC и конфигурация.
- [PIC16F1503 Silicon Errata DS80530C](https://ww1.microchip.com/downloads/en/DeviceDoc/80530C.pdf) — ограничения ревизий.
- [MPLAB X IDE](https://www.microchip.com/en-us/tools-resources/develop/mplab-x-ide) и [архив](https://www.microchip.com/en-us/tools-resources/archives/mplab-ecosystem) — MDB/Simulator; установка в нашей среде не состоялась.

## Сторонняя реализация gpsim

- Репозиторий: https://github.com/jonathan-stark/gpsim
- Эмуляция PIC16F1503: https://github.com/jonathan-stark/gpsim/blob/master/src/p1xf1xxx.cc
- Ядро/карта периферии: https://github.com/jonathan-stark/gpsim/blob/master/src/p1xf1xxx.h
- Regression PIC16F1503: https://github.com/jonathan-stark/gpsim/blob/master/regression/p1xf18xx/p16f1503.asm
- Regression NCO/CLC/PWM: https://github.com/jonathan-stark/gpsim/blob/master/regression/p1xf18xx/p16f1503_nco.asm
- Debian пакеты: https://packages.debian.org/trixie/gpsim

Важный методологический факт: тесты gpsim могут ошибаться и расходиться с datasheet. В ходе нашей сверки ожидание `OSCSTAT=0x19` признано несоответствующим маске реализованных битов; предпочтение у официальной спецификации.

## Альтернативы MPLAB

- Docker Hub mpfitzpatrick: https://hub.docker.com/r/mpfitzpatrick/mplabx-build/tags
- Docker Hub dataspeedinc: https://hub.docker.com/r/dataspeedinc/mplabx/tags
- PICsim: https://github.com/lcgamboa/picsim — похожие PIC16F1, но **список поддерживаемых моделей не содержал точного 16F1503** в исследованном дереве.
- OshonSoft PIC16 Simulator IDE: https://www.oshonsoft.com/pic16.php — Windows, trial, в нашей среде не запускался.

## Чёткая шкала достоверности

| Утверждение | Тип свидетельства |
|---|---|
| `micromusic_with_config.hex` собран, SHA зафиксирован | Проверка на локальном собственном Python-ассемблере |
| 120/120 тестов | Повторный запуск на нашем JS PIC-ядре |
| Длительные тесты 230 с, underrun=0 | Исторический отчёт эмуляции на нашем PIC-ядре |
| Сверка с опубликованными тестами gpsim | Сравнение ожидаемых регистров, повторно прогнанное на нашем JS-ядре |
| Работа в самом gpsim | **НЕ ПРОВЕРЕНА** |
| Работа в MPLAB SIM/MDB | **НЕ ПРОВЕРЕНА** |
| Работа на физическом PIC16F1503 | **НЕ ПРОВЕРЕНА** |
| Совместимость `micromusic.asm` с официальным `pic-as` | **НЕ ПРОВЕРЕНА** |

## Приоритетный следующий эксперимент

1. Запустить `CURRENT/PIC16F1503_gpsim_crosscheck/run_gpsim.sh` в Linux с установленным gpsim (сценарий требует проверки синтаксиса по версии gpsim).
2. Снять реальные W/PC/STATUS/FSR/BSR/INTCON/PIRx/TMR2/PR2/PWM3DCH/PWM3DCL + циклы и сравнить с выводом `web/pic16-core.mjs`.
3. Отдельно загрузить `firmware/micromusic_with_config.hex` в MPLAB X MDB с SIM и повторить на тех же контрольных точках.
4. Если расхождения есть, создать минимальный воспроизводимый PIC HEX, не меняя музыкальную программу до понимания аппаратной причины.
