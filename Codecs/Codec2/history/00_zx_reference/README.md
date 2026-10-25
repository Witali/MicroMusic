# Codec2 3200 → ZX Spectrum 128 / Pentagon AY demo

Это экспериментальный декодер для Z80, ориентированный на ZX Spectrum 128K / Pentagon с AY-3-8912 (или YM2149).

## Что именно реализовано

* В TRD находится `C2DEMO.C`, загрузочный адрес **32768 (0x8000)**.
* В бинарник встроено **218 кадров / 4,36 с настоящего Codec2 3200** (8 байт на кадр, 3200 бит/с), созданных установленной `libcodec2`.
* Z80 действительно разбирает формат Codec2 3200: `voiced`, 7-битный pitch, 5-битную energy и десять 5-битных LSP-difference индексов; поля Gray-coded и идут MSB-first.
* LSP difference восстанавливаются целочисленно по кодовым книгам режима 3200. Для первых трёх пар LSP вычисляются три центральные частоты.
* Вместо тяжёлого эталонного `LSP → LPC → FFT → harmonic synthesis` используется дешёвый синтез на AY:
  * voiced: три LSP-центра привязываются к ближайшим гармоникам pitch и выдаются на каналы A/B/C;
  * unvoiced: используется шум AY;
  * energy переводится в громкость AY.
* Один Codec2-кадр обрабатывается после каждого PAL interrupt 50 Гц, то есть 20 мс на кадр.

Это **не sample-identical полный Codec2 decoder**. Битовый поток на входе настоящий Codec2 3200, но синтезатор намеренно упрощён под Z80. Это proof-of-concept «Codec2-compatible parameter decoder + ZX vocoder».

## Запуск

В TR-DOS загрузить CODE-файл `C2DEMO` и вызвать адрес 32768. Типичная последовательность:

```text
LOAD "C2DEMO" CODE
RANDOMIZE USR 32768
```

Нужен Spectrum 128/Pentagon-совместимый AY на стандартных портах `0xFFFD/0xBFFD`. Демон синхронизирован с PAL 50 Гц.

Тестовая фраза: `Hello. This is Codec Two on the Z X Spectrum.`

## Файлы

* `codec2zx.asm` — исходник Z80 с подробными комментариями.
* `codec2zx.bin` — собранный CODE-бинарник.
* `codec2zx.trd` — готовый TR-DOS образ 80T/DS.
* `speech.c2zx` — встроенный настоящий Codec2 3200 поток.
* `speech8.wav` — исходная тестовая фраза, 8 kHz mono PCM16.
* `reference_codec2.wav` — тот же поток, декодированный эталонной `libcodec2` на ПК.
* `zx_ay_preview.wav` — приблизительное звучание упрощённого AY-синтеза (это не запись эмулятора ZX).
* `mini_z80asm.py` — минимальный двухпроходный ассемблер для использованного подмножества Z80.
* `validate_z80.py` — проверка машинного `decode_frame` против независимого парсера.
* `build_trd.py` / `validate_trd.py` — создание и проверка TRD.
* `encode_reference.py` — генерация настоящего Codec2 3200 через `libcodec2`.

## Сборка демо

```bash
python3 build_tables.py
python3 encode_reference.py speech8.wav speech.c2zx
python3 mini_z80asm.py codec2zx.asm codec2zx.bin codec2zx.lst
python3 validate_z80.py
python3 build_trd.py
python3 validate_trd.py
python3 make_previews.py
```

Если менять длительность `speech.c2zx`, нужно также изменить `FRAME_COUNT` в начале `codec2zx.asm` на `размер_потока / 8` и пересобрать бинарник.

## Следующий логичный шаг

Для качества речи лучше сохранить тот же парсер Codec2, но заменить «три AY-тона» на более полноценный fixed-point синтез: периодическое возбуждение по pitch + 3–5 двухполюсных формантных фильтров с коэффициентами из таблиц. Это потребует гораздо больше тактов, но приблизит звучание к настоящему вокодеру, оставаясь намного легче reference Codec2.
