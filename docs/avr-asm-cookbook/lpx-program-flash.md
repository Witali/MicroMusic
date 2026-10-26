# LPX: уменьшать Flash программы при фиксированном звуке

Измерено для ATmega328P / enhanced AVR5 с MUL, GNU ABI, AVR-GCC 7.3.0,
simavr 1.6, 16 МГц / 8 кГц. Приём касается размера программы и явно
выбираемого набора форматов. Нового ручного ASM, vendor register definitions
или заимствованного кода нет; это проектная комбинация compiler settings
и специализации существующего parser. Другие ISA/toolchains не измерялись.

## Размер отделять от данных

Считать `.text + .data − audio_bytes`, только после доказательства, что
точный массив присутствует один раз, находится во Flash и имеет ожидаемый
размер. Векторы, startup, codec tables, libgcc и playback harness остаются
в результате. Raw ELF включает метаданные; такой размер не отвечает на
вопрос о занятой программной Flash. При LTO границы функций меняются,
поэтому атрибуция исходных функций не задаёт размер новой библиотеки.

Если harness читает symbols из ELF извне, LTO/GC должен сохранить этот ABI.
Здесь одинаковый `-Wl,-u,profile_*` inventory применяется к baseline и всем
вариантам. Кроме наличия символов проверяются их storage sizes и значения
инициализированных адресов PWM/SP. Удаление измерителя не считается выигрышем.

## Проверять комбинацию, а не один флаг

Выбранный явный рецепт поверх обычных AVR target/feature options:

```text
-Os -flto -mcall-prologues -mrelax
-DLPX4_AVR_DOT_UNROLL=1 -DLPX4_FUNCTION_TUNING=0
```

Опции должны быть согласованы при компиляции и линковке через GCC driver.
Меньшая развёртка уменьшает повторение LPC tap instructions; отказ от
локального O2 позволяет глобальному Os выбирать размер. В данной комбинации
LTO, общие прологи и relaxation дали меньший код и приемлемое время.
Это измеренный результат, а не универсальная гарантия ускорения.

Официальная документация [GCC 7.3 AVR options](https://gcc.gnu.org/onlinedocs/gcc-7.3.0/gcc/AVR-Options.html)
описывает общие прологи `-mcall-prologues` и замену дальних CALL/JMP на
короткие переходы при `-mrelax`.
[GCC 7.3 LTO](https://gcc.gnu.org/onlinedocs/gcc-7.3.0/gcc/Optimize-Options.html#index-flto)
требует согласованных optimization/LTO options на обоих этапах.
Отдельное добавление function/data sections и GC к выбранной комбинации
здесь увеличило код на 12 байт в общем варианте и на 10 в v5-only.

## Выбор формата делать явным

`LPX4_COMPACT_ONLY=1` исключает v2/v3/v4 parsers и неиспользуемое состояние,
оставляя только v5 speech 4/6 с прежним синтезом. Макрос требует двух speech
feature flags. По умолчанию он выключен; defaults библиотеки unroll9/tuning7
также сохранены. Все translation units должны видеть одинаковый layout.
Специализация не превращает старый вход в новый: неподдержанный header
нужно отклонить при `begin`, а reset, tails, errors и copy semantics проверить.

Арифметический backend выбирается отдельно: ASM требует настоящих
architecture defines AVR5 и явного `LPX4_ENABLE_ASM=1`; C остаётся доступен
и на AVR. Hardware Flash access определяется platform headers независимо
от этого выбора. Нельзя подменять реальные CPU/memory-model defines.

## Измеренный итог и ограничения

На восьми фиксированных enhanced v5 потоках общая программа без аудио
9171–9172 → 7889–8030 байт; v5-only → 5909–5910 байт. В неё входит прежний
harness. Static SRAM 1105 → 1105 / 1085 байт. Средние decode wall cycles
958,490 → 846,641 / 785,019, включая IRQ и instrumentation.
Размер меняется с размещением/длиной встроенного массива при LTO/relaxation.

Полный полезный PWM одинаков для всех 16 новых основных AVR images;
общая сборка также прошла 91 frozen legacy stream. Для обоих профилей
проверены 64k-sample непрерывные normal и +100 IRQ controls: underruns=0.
C fallback даёт точные значения, но 3128–3174 cycles/sample и пропуски;
real-time 8 кГц для него не заявляется.

125 host tests (один optional skip), по 613391 ASan/UBSan mutation/reset cases
для двух parser profiles и по 5768584 arithmetic cases для C/ASM/generic
под выбранными flags с активными IRQ проверяют тот же reference output.
Проверка ABI включает r1 zero errors. Stack после ready: общий 124 байта,
v5-only 105, minimum observed margin 819/858; startup/worst-case не доказан.
Это simulator admission для queue512/prefill384/LPC segments2, не проверка
физической платы или всех возможных голосов.

[Точные flags, hashes, per-image measurements и границы](../../Codecs/LPX/research/speech-flash-2026-10-26/README.md),
[воспроизводимый bounded screen и полная PWM-проверка](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/benchmark_speech_flash.py).
