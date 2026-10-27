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

## Тот же рецепт для legacy v2/v3

Дополнительная измеренная область применения: 27 полных четырёхсекундных
записей, выбранные 8/12/16 кбит/с, v3 features24. Явно выключены оба speech
parser flags, `LPX4_COMPACT_ONLY=0`; поэтому v5-only layout здесь неприменим.
Остальные CPU/ABI/toolchain, queue512/prefill384, segments2 и ASM opt-in
такие же. Библиотечные defaults не меняются. Использован тот же compiler
factory; восемь прежних common speech command lists остались точными.

На тех же selected streams unroll9/tuning7 → unroll1/tuning0 с
`-Os -flto -mcall-prologues -mrelax`: средние decode wall cycles
804,628 → 705,270 (8), 835,160 → 730,176 (12), 865,255 → 753,662 (16).
Программа без точно проверенного audio array — 6512–6514 байт;
static SRAM1102. В 77 уникальных полных ELF полезный PWM точен,
underruns=0; minimum observed stack margin после ready828 байт.

Дополнительно девять непрерывных 64k-sample controls: normal/+100 IRQ/C
для каждого bitrate. Все ASM без пропусков, C точен по значениям, но
3164–3196 cycles/sample и underruns. Это simulator admission измеренных
потоков, не startup stack proof или гарантия другого приложения.
Новых арифметических ASM путей нет; C fallback и аппаратный Flash access
остаются независимыми. Полные source/toolchain/firmware hashes и memory
accounting в [legacy profile study](../../Codecs/LPX/research/encoder-profiles-2026-10-26/README.md).

## Общий сброс состояния LPX: измеренный рефакторинг

Для того же ATmega328P / enhanced AVR5 с MUL, GNU ABI, AVR-GCC 7.3.0,
simavr 1.6 и прежних small-code flags от 27.10.2026: вынести одинаковую
очистку синтеза из конструктора и `begin()` в одну частную
[`resetSynthesis()`](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/src/Lpx4HybridCore.cpp).
Группировать по одинаковому контракту: фильтры, массивы спектра/истории,
LPC cache и instrumentation. Парсер, вход, progress и error оставить
в соответствующих lifecycle-функциях, чтобы сохранить неудачный restart.
Порядок полей и layout не меняются. Это C++-рефакторинг размера программы;
новых ASM и изменений выбора C/ASM нет.

На восьми тех же потоках общая программа без аудио
7889–8030 → **7729–7870 байт** (−160 на поток); v5-only
5909–5910 → **5753–5754 байт** (−156). Static SRAM и наблюдавшийся
stack margin прежние. Полные decode wall-cycle totals не изменились;
полезный PWM точен, normal/+100 IRQ controls без пропусков.
Подтверждено 46 host tests, 91 legacy golden stream и по 605670
ASan/UBSan mutation/reset cases для двух layouts. C fallback точен
по значениям, его прежние deadline misses сохраняются.

Отдельно удалена недостижимая ветка LPC, закрытая безусловным макросом,
и частный forwarding wrapper. Мёртвая ветка не занимала Flash:
экономию нельзя приписывать числу удалённых строк. Для других
toolchains/workloads эффект общего helper требует повторного измерения.
[Подробности, before/after hashes, flags и ограничения](../../Codecs/LPX/research/decoder-refactor-2026-10-27/README.md).

## Ещё меньше Flash LPX: общие readers и один цикл LPC

Второй проход от `5dea80be`: те же ATmega328P / enhanced AVR5 с MUL,
GNU ABI, AVR-GCC 7.3.0, simavr 1.6, 16 МГц / 8 кГц, unroll 1 / tuning 0,
`-Os -flto -mcall-prologues -mrelax`. Измеренный выигрыш касается Flash;
новых ASM и изменений C/ASM selection нет.

Общий `resetSynthesis()` расширен до `resetState()`: одинаковые scalar
parser/synthesis fields и каждый именованный массив через свой `sizeof`.
Размеры между соседними полями не предполагаются. Публичную metadata при
неудачном `begin()` сохранить. Для v4 accepted count ≤64000 позволяет
16-битную геометрию пакетов; v5 untrusted payload+22 по-прежнему требует
широкой проверки. Rice delta ограничен 7 битами, поэтому signed8 достаточен.

Один цикл из 10 коэффициентов выбирает независимые P/Q полиномы по чётности,
сохраняя степени и порядок вкладов. Два соседних cosine узла используют
общую reflection: отрицательный интервал начинается в `-hi`, а slope
остаётся `hi-lo`; floor rounding сохраняется. `readOne()` делегирует
`readBits(1)`, включая прежний instrumentation, при инварианте нулевых
неиспользуемых cache bits. Убрано принудительное встраивание pitch predictor.

На восьми фиксированных потоках common 7729–7870 → **7225–7320 Б**
(−504…550), compact-only 5753–5754 → **5363–5364 Б** (−390).
Static SRAM прежняя. Среднее decode wall time выросло **3,09% / 2,51%**;
полезный PWM точен, normal/+100 IRQ controls без underruns. After-ready
stack margin 819→845  / 858→882 Б не является worst-case/startup proof.
C fallback остаётся точным, его 8 кГц deadline не обеспечен.

Полный вывод сверяют с frozen model, а новый anchor regression сохраняет
digest 34816 преобразований старого ядра. Проверены 764 stream/config pairs,
все 4096 cosine inputs, 91 golden stream и по 605670 ASan/UBSan reset cases.
[Подробности, flags, source hashes и отклонённые варианты](../../Codecs/LPX/research/decoder-flash-pass2-2026-10-27/README.md).
