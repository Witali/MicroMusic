# Итог LPX: остановка после трёх слабых раундов

Цикл завершён после19 раундов. Первые три последовательных принятых выигрыша
≤1% — раунды17/18/19: **0%,0%,0,175483%**. В17 отклонён более медленный
adaptive LPC, в18 — почти нулевой выигрыш split shifts ценой кода.
После выполнения условия новых оптимизаций не делалось.

Относительно `5d608739`, на тех же91 потоках/2912000 samples:

| Метрика | Начало | Итог |
| --- | --- | --- |
| Сумма decode wall cycles | 3942532013 | 2495466530 |
| Время декодирования | 100% | 63.296037% |
| Flash одинаковых firmware images | baseline | -496 Б на каждом из91 ELF |
| Статическая SRAM firmware | 1084 Б | 1102 Б (+18 Б) |
| Минимальный измеренный stack margin | — | 823 Б |

Снижение времени **36.703963%**, коэффициент ускорения **1.579878×**.
Это simavr/ATmega328P16МГц,8кГц,queue512/prefill384/unroll9,v3mask24,
AVR-GCC7.3 -Os с сохранённым локальным O2 и явно включённым ASM.
Wall intervals включают активные IRQ и profiling stores; это не чистая
доля арифметических инструкций процессора. Размеры относятся к полной
прошивке с тем же payload/harness; постоянная разница Flash отражает код/таблицы.

## Качество и границы проверок

Свежий [quality audit](round-19-quality.json) подтвердил полное равенство
native PCM16/PWM frozen-эталонам и полезного AVR PWM исходному baseline.
Различий выходных samples **0**; на91 основных firmware **0 underrun**.
Это равенство прежнему декодеру, а не отсутствие потерь LPX относительно WAV.
Сжатые входы, их hashes и параметры сравнения не менялись между раундами.

99 host-тестов, reference/rotation ×segments1/2/4 ×v2/v3, partial/restart,
independent copy/assignment snapshots и566610 ASan/UBSan mutation/reset
случаев прошли. Арифметический header byte-identical раунду13: его девять
C/ASM/generic ×unroll1/3/9 сборок по5768584 проверок с IRQ/r1 применимы;
новый запуск этой неизменной арифметики не заявляется.

Шесть8-секундных контролей (enhanced16,enhanced8,legacy; обычный IRQ и
+100 cycles на audio IRQ) прошли без пропусков. Физической платы нет,
все timing/support выводы ограничены указанным симулятором и workloads.

## Дополнительная проверка C/ASM и настроек

Свежий `tools/verify_decoder_configs.py` собирает варианты без правки src,
вводя только фиксированные output-equivalent defines при AVR compilation.
На одном и том же тяжёлом8-секундном входе все64000 полезных PWM bytes
совпали с текущим native-default выводом и между всеми пятью вариантами.

| Вариант | Wall cycles/sample | Underrun | Flash Б | Static SRAM Б |
| --- | --- | --- | --- | --- |
| c-default | 2787.336 | 27823 | 23348 | 1102 |
| c-unscaled | 2757.616 | 26877 | 23326 | 1102 |
| asm-default | 950.386 | 0 | 23320 | 1102 |
| asm-linear | 976.219 | 0 | 23302 | 1082 |
| asm-reference | 1097.869 | 0 | 22832 | 1082 |

**C fallback корректен по значениям samples, но не выдерживает8кГц на этом
тяжёлом AVR workload**: пропуски означают реальное нарушение времени
воспроизведения. Его не объявляем real-time профилем. Поддержанный здесь
реальный-time путь требует явного `LPX4_ENABLE_ASM=1`. ASM default,
линейная история и reference-control вариант прошли эту проверку без пропусков.
Полные defines, source/ELF/HEX hashes и compiler options находятся в
[configuration evidence](final-configurations.json).

`final-audit.json` проверяет baseline hashes, равенство набора/settings,
cycle sums, каждый процент, source hashes и первый момент выполнения
критерия остановки. История сохранена отдельными focused commits;
непринятые prototypes и их scope сохранены отдельно. Experimental patches
в cookbook воспроизводятся на исторической source-базе раунда16, до
последующей перестановки anchors; в production они не включены.

Push, публикация и upload исходного аудио не выполнялись.
