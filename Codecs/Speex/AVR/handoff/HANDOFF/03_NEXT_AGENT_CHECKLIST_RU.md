# ИНСТРУКЦИЯ СЛЕДУЮЩЕМУ АГЕНТУ

## Цель
Довести исходный Xiph Speex 1.2.1 Narrowband mode-3 fixed-point decoder до стандартно-совместимого реального воспроизведения на ATmega328P @ 16MHz, ≤2048 B общей SRAM, ≤32 KiB Flash, с устойчивым временем на кадр ≤20ms вместе с PCM/PWM/ISR. Не трогать R4 baseline.

## Ключевые каталоги
- `UNPACKED/09_Xiph_Upstream_Port_WIP_ACTIVE/.../README_RU.md` — описание всего незавершённого upstream-порта и commands. Запустить `tests/run_local_tests.sh` как быстрый sanity-check.
- `UNPACKED/09_Xiph_Upstream_Port_WIP_ACTIVE/.../tools/get_speex_source.py` — загрузка и проверка SHA256 официального оригинального исходника.
- `UNPACKED/09_Xiph_Upstream_Port_WIP_ACTIVE/.../tools/apply_upstream_port.py` — воспроизводимая правка upstream.
- `UNPACKED/09_Xiph_Upstream_Port_WIP_ACTIVE/.../tests/compare_upstream_versions.sh` — будущая проверка real upstream decode.
- `UNPACKED/08_R4_Cache10Fused_REFERENCE/.../` — контрольный self-written декодер (READ ONLY); тесты и звуковые потоки.
- `UNPACKED/02_Timing_and_Interpreter/` и `UNPACKED/05_FastLPC_ASM/` — AVR cycle interpreter и ассемблерные оптимизации.

## Минимально необходимый план эксперимента
1. Restore original `speex-1.2.1.tar.gz` verified SHA. Не выдавать system libspeex.so и собственную R4 за исходники оригинальной версии.
2. Build fixed-point reference, with no encoder, no WB, no enhancer/highpass на первом этапе; verify raw frame parse, PCM.
3. Enable compact_lsp; compare byte-identical decoded PCM for all 1058 test frames and, если возможно, реальные женские/мужские RU/EN голоса.
4. Instrument peak memory (scratch high-water, peak recursion, signal lifetime), remove 16K scratch pool and avoid buffer collisions.
5. Separate safe exact changes and experiments; test `SPEEX_AVR_TIGHT_EXC` for full decoded PCM only after safe baseline. If mismatch, discard or isolate experimental.
6. Move codebooks + lookup tables to PROGMEM and fix pointer access. Add an exhaustive table value checksum test for AVR.
7. Compile GCC AVR, report actual `.elf` sections and stack, run an ISA simulator or on-chip GPIO timing on worst-case frames.
8. Only then port MUL and LPC asm and benchmark **same** encoder inputs, GCC flags and memory layout against reference and unchanged R4.

## Перед отчётом пользователю
Всегда разделяйте: (a) тесты отдельных арифметических функций; (b) host PCM reference; (c) AVR LLVM model; (d) avr-gcc assembly; (e) реальные такты/звук платы. Не присваивайте метрики исходного R4 новому upstream-порту.
