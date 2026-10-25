# Инженерные заметки и итоги оптимизации

## Почему по сравнению с исходным Codec2 это существенно быстрее

Официальный Codec2 3200 использует полноценную реконструкцию гармонического спектра и IFFT 512 точек, с обработкой float. Этому требуется существенно больше памяти и операций, чем доступно ATtiny13A. Для ATtiny13A сделан **отдельный ограниченный по качеству синтезатор**, который реконструирует только voicing, pitch, energy и первые три пары LSP, не пытается восстановить PCM эталонного Codec2.

### Оптимизации

1. **Битовый разбор без таблиц и без умножения.** Позиция бита поддерживается маской в r15, X указывает на текущий байт; Gray декодируется сразу по чётности прочитанных бит, без отдельного цикла преобразования.
2. **LSPD scalar quantiser без таблиц.** Семь индексов стандартного семейства `delta=index+1` и три широких `index<8 ? index+1 : 2*index-6` в единицах 25 Гц. Нужны только первые 6 LSP для трёх пар; последние 4 намеренно не используются в аудиосинтезе.
3. **Pitch quantisation без умножения.** f0 единицы 25 Гц: `2+(pitch>>3)-(pitch>>6)` (вместо более точной исходной линейной карты). Погрешность на двух тестовых потоках: MAE ~6.5 Гц, RMS ~7.9 Гц, макс ~21.9 Гц. Это отдельное приближение качества.
4. **Nearest harmonic без аппаратного деления.** Для трёх формант многократное прибавление малой частоты f0, максимум несколько десятков итераций; выполняется лишь 50 раз/с, не на каждый отсчёт.
5. **16-битный DDS с точным коэффициентом 205.** Перевод `u` в частотный шаг `u*205` делается сдвигами/сложениями: `205=128+64+8+4+1`. Частота после такого преобразования составляет `25.0244 Hz` на единицу вместо идеальной 25Hz (+0.098%). Процессор не имеет MUL.
6. **Генерация PCM без таблиц.** Каждая из трёх фаз обновляется двумя восьмибитными ADD/ADC и SRAM-обращениями. Вокализованные сегменты — взвешенная сумма 3 прямоугольных волн; невокализованные — маленький xorshift PRNG. Суммарная амплитуда не превышает 105 единиц из 128, поэтому переполнение PCM отсутствует даже для energy=31.
7. **Частота сэмплирования без второго таймера.** Fast PWM 37.5kHz на OC0B PB1, overflow 37.5kHz, fractional accumulator +16 modulo75 создаёт 8000 samples/second в среднем; интервалы 4 или 5 периодов PWM.

## Метрики

Core object section `.text`: 572 bytes. One-frame autonomous example `.text`: 716 bytes. Static SRAM (including 8B Codec2 input): 29 bytes; stack demo estimated ~11B max. Core worst-case 2,361 cycles to parse a crafted random frame, plus <=83 cycles for each of 160 samples (conservative bound 15,641 cycles / 20ms). Even this is only about 8.15% available 192,000 CPU cycles. These metrics are *source-level AVR instruction simulation* plus Clang code sizes, NOT oscilloscope or real-time measurement on silicon. Demo Timer0 interrupt overhead is outside the core bound; an executed instruction-level ISR test gives 42–131 cycles per overflow, mean 60.88 cycles, safely inside 256 cycles (hardware still untested).

## Проверка исходных параметров

365 Codec2 3200 frames: every field `voiced0(1) voiced1(1) pitch(7) energy(5) LSPD_0..9(5)` matched `libcodec2.unpack`, starting each frame at bit 0. The original libcodec2 `decode_lspds_scalar` gave cumulative frequencies equivalent to the arithmetic reconstruction to within 0.000151 Hz float rounding across 3650 coefficients. Test scripts compare *the same standard bitstream*, not a special converter-generated stream.

## Ключевой компромисс

Это **не полноценный декодер Codec2**. Он несовместим по форме синтеза с оригинальной `libcodec2` и обычно звучит намного хуже, даже если входные кадры синтаксически стандартные. Дальнейшее повышение качества рациональнее искать в 1–2 формантных резонаторах и постепенной интерполяции параметров, а не в ещё более агрессивном битовом парсере (он и так очень дёшев по тактам).

Для полноценного синтеза речи высокого качества на 9.6MHz нужен отдельный профиль с несколькими KB Flash/констант и тестами worst-case. Нельзя выдавать малый процент CPU этой упрощённой реализации за доказательство, что полноценный Codec2 real-time работает на ATtiny13A.
