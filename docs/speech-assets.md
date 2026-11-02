# Речевые примеры: исходники, сжатие и прошивки

Общий порядок задаёт [web-player/speech-examples.json](../web-player/speech-examples.json). Качества относятся к выбранной фразе и микроконтроллеру. ATtiny13A использует один выбранный образ; LPX имеет собственные варианты качества.

## Исходные записи

Используются только уже открытые записи проекта. Новые варианты не обрезают фразы и не меняют скорость. Изменение частоты дискретизации сохраняет время; Tiny добавляет только нулевой хвост последнего 64-отсчётного блока.

| № | Фраза | Исходный WAV | Гц / отсчётов | SHA-256 |
| --- | --- | --- | --- | --- |
| 01 | Чего тебе нужно? | [web-player/audio/originals/chego.wav](../web-player/audio/originals/chego.wav) | 7500 / 9216 | `c6cdbd26696bdd11695f2491f1558dd246a6f8109fd400e37d292a4d38cdb08c` |
| 02 | Что ж ты не отвечаешь? | [web-player/audio/originals/otvechaesh.wav](../web-player/audio/originals/otvechaesh.wav) | 7500 / 7936 | `96c09f80396643dd80efb9c5c8557d83359eeb829a0b855a7f8f5c32bbff0b96` |
| 03 | Сова! Открывай! Медведь пришёл! | [web-player/audio/originals/vinni.wav](../web-player/audio/originals/vinni.wav) | 7500 / 22272 | `749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03` |
| 04 | И того, и другого, и можно без хлеба | [web-player/audio/lpx-bread/original.wav](../web-player/audio/lpx-bread/original.wav) | 8000 / 19200 | `f744f2f8aa554c0da3361f309f9226d86484ca06d5cfd7b2925afad444a19d31` |

## LPX: каждый сжатый файл

Новые первые три фразы: [tools/prepare-shared-speech.py](../tools/prepare-shared-speech.py) → `speech_v4.encode` (профиль 4 или 6, `pre=13926`, `bandwidth=0.97`, `allow_zero_scale=False`) → точная переупаковка `speech_compact.repack` в LPX v5. Вход 7500 → 8000 Гц через `scipy.signal.resample_poly(16, 15)`, PCM16, без усиления. Каждый результат проверяется по независимой модели и двум нативным декодерам: общему и v5-only.

Варианты bread сохранены из прежнего набора побайтно. Их прежние скрипты, параметры и экспериментальный формат S15 описаны в [web-player/audio/lpx-bread/README.md](../web-player/audio/lpx-bread/README.md). Новая сборка Nano переиспользует эти потоки; S15 на Nano не заявлен.

| Фраза | LPX-файл | Формат / профиль | Байт | Связанный WAV | Скрипт |
| --- | --- | --- | ---: | --- | --- |
| chego | [web-player/audio/lpx-speech/chego/compact.lpx](../web-player/audio/lpx-speech/chego/compact.lpx) | LPX v5 / 4 | 536 | [web-player/audio/lpx-speech/chego/compact.wav](../web-player/audio/lpx-speech/chego/compact.wav) | [tools/prepare-shared-speech.py](../tools/prepare-shared-speech.py) |
| chego | [web-player/audio/lpx-speech/chego/quality.lpx](../web-player/audio/lpx-speech/chego/quality.lpx) | LPX v5 / 6 | 791 | [web-player/audio/lpx-speech/chego/quality.wav](../web-player/audio/lpx-speech/chego/quality.wav) | [tools/prepare-shared-speech.py](../tools/prepare-shared-speech.py) |
| otvechaesh | [web-player/audio/lpx-speech/otvechaesh/compact.lpx](../web-player/audio/lpx-speech/otvechaesh/compact.lpx) | LPX v5 / 4 | 470 | [web-player/audio/lpx-speech/otvechaesh/compact.wav](../web-player/audio/lpx-speech/otvechaesh/compact.wav) | [tools/prepare-shared-speech.py](../tools/prepare-shared-speech.py) |
| otvechaesh | [web-player/audio/lpx-speech/otvechaesh/quality.lpx](../web-player/audio/lpx-speech/otvechaesh/quality.lpx) | LPX v5 / 6 | 692 | [web-player/audio/lpx-speech/otvechaesh/quality.wav](../web-player/audio/lpx-speech/otvechaesh/quality.wav) | [tools/prepare-shared-speech.py](../tools/prepare-shared-speech.py) |
| vinni | [web-player/audio/lpx-speech/vinni/compact.lpx](../web-player/audio/lpx-speech/vinni/compact.lpx) | LPX v5 / 4 | 1243 | [web-player/audio/lpx-speech/vinni/compact.wav](../web-player/audio/lpx-speech/vinni/compact.wav) | [tools/prepare-shared-speech.py](../tools/prepare-shared-speech.py) |
| vinni | [web-player/audio/lpx-speech/vinni/quality.lpx](../web-player/audio/lpx-speech/vinni/quality.lpx) | LPX v5 / 6 | 1862 | [web-player/audio/lpx-speech/vinni/quality.wav](../web-player/audio/lpx-speech/vinni/quality.wav) | [tools/prepare-shared-speech.py](../tools/prepare-shared-speech.py) |
| bread | [web-player/audio/lpx-bread/compact.lpx](../web-player/audio/lpx-bread/compact.lpx) | LPX v5 / 4 | 1008 | [web-player/audio/lpx-bread/compact.wav](../web-player/audio/lpx-bread/compact.wav) | [Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/encode_speech_voice.py](../Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/encode_speech_voice.py) |
| bread | [web-player/audio/lpx-bread/quality.lpx](../web-player/audio/lpx-bread/quality.lpx) | LPX v5 / 6 | 1899 | [web-player/audio/lpx-bread/quality.wav](../web-player/audio/lpx-bread/quality.wav) | [Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/encode_speech_voice.py](../Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/encode_speech_voice.py) |
| bread | [web-player/audio/lpx-bread/low15.lpx](../web-player/audio/lpx-bread/low15.lpx) | S15 v8 / 15 | 417 | [web-player/audio/lpx-bread/low15.wav](../web-player/audio/lpx-bread/low15.wav) | [Codecs/LPX/research/lpx-s15-2026-11-01/README.md](../Codecs/LPX/research/lpx-s15-2026-11-01/README.md) |

WAV в этой таблице — точные 8-битные PWM-отсчёты декодера в PCM16: `(duty - 128) * 256`. Они служат превью ATtiny88 и Nano, не являются записью аналогового выхода платы.

## Arduino Nano: полные HEX

Сборщик [tools/build-nano-speech-catalog.py](../tools/build-nano-speech-catalog.py) встраивает указанный LPX в существующий `AVR_V5_PLAYER`: ATmega328P, 16 МГц, FIFO 256 / prefill 192, D3 / OC2B, 8 кГц. ASM включается отдельным `--enable-asm`; без него выбран C. Все восемь сохранённых HEX проверены в simavr 1.6 с активными IRQ: весь поток, точное совпадение с WAV и ноль underruns. Физическая плата не проверялась.

| HEX | LPX | Код / полный Flash, Б | Static SRAM, Б | Отсчётов / пропусков |
| --- | --- | ---: | ---: | --- |
| [web-player/firmware/arduino-nano/lpx-nano-chego-compact.hex](../web-player/firmware/arduino-nano/lpx-nano-chego-compact.hex) | chego / compact | 4574 / 5110 | 756 | 9831 / 0 |
| [web-player/firmware/arduino-nano/lpx-nano-chego-quality.hex](../web-player/firmware/arduino-nano/lpx-nano-chego-quality.hex) | chego / quality | 4573 / 5364 | 756 | 9831 / 0 |
| [web-player/firmware/arduino-nano/lpx-nano-otvechaesh-compact.hex](../web-player/firmware/arduino-nano/lpx-nano-otvechaesh-compact.hex) | otvechaesh / compact | 4574 / 5044 | 756 | 8466 / 0 |
| [web-player/firmware/arduino-nano/lpx-nano-otvechaesh-quality.hex](../web-player/firmware/arduino-nano/lpx-nano-otvechaesh-quality.hex) | otvechaesh / quality | 4574 / 5266 | 756 | 8466 / 0 |
| [web-player/firmware/arduino-nano/lpx-nano-vinni-compact.hex](../web-player/firmware/arduino-nano/lpx-nano-vinni-compact.hex) | vinni / compact | 4573 / 5816 | 756 | 23757 / 0 |
| [web-player/firmware/arduino-nano/lpx-nano-vinni-quality.hex](../web-player/firmware/arduino-nano/lpx-nano-vinni-quality.hex) | vinni / quality | 4574 / 6436 | 756 | 23757 / 0 |
| [web-player/firmware/arduino-nano/lpx-nano-bread-compact.hex](../web-player/firmware/arduino-nano/lpx-nano-bread-compact.hex) | bread / compact | 4574 / 5582 | 756 | 19200 / 0 |
| [web-player/firmware/arduino-nano/lpx-nano-bread-quality.hex](../web-player/firmware/arduino-nano/lpx-nano-bread-quality.hex) | bread / quality | 4573 / 6472 | 756 | 19200 / 0 |

## Speex на Arduino Nano: три фразы, три битрейта

Сборщик [tools/build-speex-nano-catalog.py](../tools/build-speex-nano-catalog.py) использует те же полные открытые исходники первых трёх фраз. FFmpeg / libspeex 1.2.1 кодирует CBR с complexity 10: NB 2,15 кбит/с при 8 кГц, WB 3,95 и 9,8 кбит/с при 16 кГц. VAD, DTX и ABR выключены. Ресэмплирование сохраняет длительность и уровень; добавляется 80 мс нулевого хвоста и выравнивание до полного кадра, задержка кодека не вырезается. Ogg-заголовки и комментарии не публикуются.

Исходники записаны при 7500 Гц: режим WB с выходом 16 кГц не восстанавливает отсутствующие в них высокие частоты. Номинальные битрейты отличаются от хранения с выравниванием пакетов по байтам: 2,4 / 4,0 / 10,0 кбит/с соответственно.

PCM захватывается из исполняемого AVR ASM-декодера, затем полный связанный плеер проверяется против этого захвата с активными таймерами и IRQ в AVR8js 0.21.1. WAV содержит все реальные PWM-отсчёты `(duty - 128) * 256`, включая задержку и хвост. Это проверка транспортировки и тайминга; независимые проверки арифметики кодека сохранены в [Codecs/Speex/AVR/reports/prepared-admission.json](../Codecs/Speex/AVR/reports/prepared-admission.json). Полный C-декодер при подготовке этих примеров не исполняется. Аналоговый выход физической платы не измерялся.

Все опубликованные прошивки используют **D3 / PD3 / OC2B**, как LPX: PWM 62,5 кГц, PCM 8 или 16 кГц. При сборке можно выбрать `--pwm-pin 3` или `--pwm-pin 9` (`SPEEX_AVR_PWM_PIN=3/9`). Сборщик каталога по умолчанию выбирает D3; низкоуровневые сборщики сохраняют прежний D9. Выбор арифметики C/ASM независим от выбора контакта.

| Фраза / профиль | Сжатый поток | PWM WAV | HEX | Код / полный Flash, Б | Static / свободная SRAM на пике, Б | Отсчётов / пропусков |
| --- | --- | --- | --- | ---: | ---: | --- |
| chego / Speex NB · 2,15 кбит/с | [web-player/audio/speex-speech/chego/nb215.spxraw](../web-player/audio/speex-speech/chego/nb215.spxraw) | [web-player/audio/speex-speech/chego/nb215.wav](../web-player/audio/speex-speech/chego/nb215.wav) | [web-player/firmware/arduino-nano/speex-nano-chego-nb215.hex](../web-player/firmware/arduino-nano/speex-nano-chego-nb215.hex) | 12704 / 13100 | 1231 / 698 | 10560 / 0 |
| chego / Speex WB · 3,95 кбит/с | [web-player/audio/speex-speech/chego/wb395.spxraw](../web-player/audio/speex-speech/chego/wb395.spxraw) | [web-player/audio/speex-speech/chego/wb395.wav](../web-player/audio/speex-speech/chego/wb395.wav) | [web-player/firmware/arduino-nano/speex-nano-chego-wb395.hex](../web-player/firmware/arduino-nano/speex-nano-chego-wb395.hex) | 20450 / 21110 | 1406 / 449 | 21120 / 0 |
| chego / Speex WB · 9,8 кбит/с | [web-player/audio/speex-speech/chego/wb98.spxraw](../web-player/audio/speex-speech/chego/wb98.spxraw) | [web-player/audio/speex-speech/chego/wb98.wav](../web-player/audio/speex-speech/chego/wb98.wav) | [web-player/firmware/arduino-nano/speex-nano-chego-wb98.hex](../web-player/firmware/arduino-nano/speex-nano-chego-wb98.hex) | 17310 / 18960 | 1409 / 450 | 21120 / 0 |
| otvechaesh / Speex NB · 2,15 кбит/с | [web-player/audio/speex-speech/otvechaesh/nb215.spxraw](../web-player/audio/speex-speech/otvechaesh/nb215.spxraw) | [web-player/audio/speex-speech/otvechaesh/nb215.wav](../web-player/audio/speex-speech/otvechaesh/nb215.wav) | [web-player/firmware/arduino-nano/speex-nano-otvechaesh-nb215.hex](../web-player/firmware/arduino-nano/speex-nano-otvechaesh-nb215.hex) | 12704 / 13046 | 1231 / 698 | 9120 / 0 |
| otvechaesh / Speex WB · 3,95 кбит/с | [web-player/audio/speex-speech/otvechaesh/wb395.spxraw](../web-player/audio/speex-speech/otvechaesh/wb395.spxraw) | [web-player/audio/speex-speech/otvechaesh/wb395.wav](../web-player/audio/speex-speech/otvechaesh/wb395.wav) | [web-player/firmware/arduino-nano/speex-nano-otvechaesh-wb395.hex](../web-player/firmware/arduino-nano/speex-nano-otvechaesh-wb395.hex) | 20450 / 21020 | 1406 / 449 | 18240 / 0 |
| otvechaesh / Speex WB · 9,8 кбит/с | [web-player/audio/speex-speech/otvechaesh/wb98.spxraw](../web-player/audio/speex-speech/otvechaesh/wb98.spxraw) | [web-player/audio/speex-speech/otvechaesh/wb98.wav](../web-player/audio/speex-speech/otvechaesh/wb98.wav) | [web-player/firmware/arduino-nano/speex-nano-otvechaesh-wb98.hex](../web-player/firmware/arduino-nano/speex-nano-otvechaesh-wb98.hex) | 17311 / 18736 | 1409 / 450 | 18240 / 0 |
| vinni / Speex NB · 2,15 кбит/с | [web-player/audio/speex-speech/vinni/nb215.spxraw](../web-player/audio/speex-speech/vinni/nb215.spxraw) | [web-player/audio/speex-speech/vinni/nb215.wav](../web-player/audio/speex-speech/vinni/nb215.wav) | [web-player/firmware/arduino-nano/speex-nano-vinni-nb215.hex](../web-player/firmware/arduino-nano/speex-nano-vinni-nb215.hex) | 12704 / 13622 | 1231 / 698 | 24480 / 0 |
| vinni / Speex WB · 3,95 кбит/с | [web-player/audio/speex-speech/vinni/wb395.spxraw](../web-player/audio/speex-speech/vinni/wb395.spxraw) | [web-player/audio/speex-speech/vinni/wb395.wav](../web-player/audio/speex-speech/vinni/wb395.wav) | [web-player/firmware/arduino-nano/speex-nano-vinni-wb395.hex](../web-player/firmware/arduino-nano/speex-nano-vinni-wb395.hex) | 20452 / 21982 | 1406 / 449 | 48960 / 0 |
| vinni / Speex WB · 9,8 кбит/с | [web-player/audio/speex-speech/vinni/wb98.spxraw](../web-player/audio/speex-speech/vinni/wb98.spxraw) | [web-player/audio/speex-speech/vinni/wb98.wav](../web-player/audio/speex-speech/vinni/wb98.wav) | [web-player/firmware/arduino-nano/speex-nano-vinni-wb98.hex](../web-player/firmware/arduino-nano/speex-nano-vinni-wb98.hex) | 17311 / 21136 | 1409 / 450 | 48960 / 0 |

Для воспроизведения нужны AVR-GCC 7.3.0 проекта, Node.js, зависимости AVR8js из `Codecs/Speex/AVR` и FFmpeg с libspeex. Контрольные суммы исходников, точных потоков, WAV и HEX, а также результаты IRQ-проверок находятся в [web-player/firmware-speex-atmega328p.json](../web-player/firmware-speex-atmega328p.json).

```text
python tools/build-speex-nano-catalog.py --avr-gcc /path/to/avr-gcc --node /path/to/node --pwm-pin 3 --publish
```

## ATtiny13A: выбранные образы

Основные три образа сохранены в [web-player/hq4-firmware.json](../web-player/hq4-firmware.json); добавленная фраза — в [web-player/firmware-attiny13a-speech-extra.json](../web-player/firmware-attiny13a-speech-extra.json). Каталоги содержат полный Flash HEX и при необходимости EEPROM HEX, контрольные суммы и пути исходников.

| Фраза | Кодек | Сохранённый источник | Скрипт сборки / подбора | Flash / EEPROM, Б |
| --- | --- | --- | --- | ---: |
| chego | tiny-period | [ATtiny13A/Sound/research/tiny-speech/chego/model.json](../ATtiny13A/Sound/research/tiny-speech/chego/model.json) | [tools/build-tiny-speech.py](../tools/build-tiny-speech.py) | 1024 / 64 |
| otvechaesh | tiny-period | [ATtiny13A/Sound/research/tiny-speech/otvechaesh/model.json](../ATtiny13A/Sound/research/tiny-speech/otvechaesh/model.json) | [tools/build-tiny-speech.py](../tools/build-tiny-speech.py) | 1024 / 64 |
| vinni | hq4 | [ATtiny13A/Sound/codec/release/vinni/speech.hq](../ATtiny13A/Sound/codec/release/vinni/speech.hq) | [tools/build-hq4-oneshot.py](../tools/build-hq4-oneshot.py) | 1024 / 0 |
| bread | tiny-period | [ATtiny13A/Sound/research/shared-speech/bread-model.json](../ATtiny13A/Sound/research/shared-speech/bread-model.json) | [tools/build-shared-tiny-speech.py](../tools/build-shared-tiny-speech.py) | 1014 / 64 |

Для bread сравнивались оба режима высоты, словари 1/2/4/8 периодов, региональное удержание параметров и по 3000 предложений точного поиска на режим. Выбран `spectrogram-noise`: 1014 Б Flash + 64 Б EEPROM. Полная матрица, критерий выбора и проверки сохранены в [ATtiny13A\Sound\research\shared-speech\bread-selection.json](../ATtiny13A\Sound\research\shared-speech\bread-selection.json). Субъективное превосходство автоматически не утверждается; варианты для прослушивания находятся в локальном `build/shared-speech/`.

Необязательное первоначальное измерение воспроизводит [tools/probe-tiny-speech-budget.py](../tools/probe-tiny-speech-budget.py): открытый bread-исходник, словарь 8 периодов, 2 старта, ассемблированный кандидат 1074 Б Flash + 64 Б EEPROM. Он превышает Flash; это измерение размера, без допуска воспроизведения. Результаты остаются в `build/shared-speech/tiny-initial-probe/` и не меняют выбранную прошивку.

```text
python tools/probe-tiny-speech-budget.py --avr-bin /path/to/avr/bin
```

### Подбор менее шумного варианта

После замечания о шуме выполнен отдельный поиск [tools/refine-shared-tiny-noise.py](../tools/refine-shared-tiny-noise.py). Он сравнивает исходник и точный PWM без подгонки громкости, на общей временной шкале: STFT 256 и 1024, уровни остаточного шума, варианты высоты и ограниченное уточнение словаря/параметров. Порог разборчивости и формула спектральной оценки сохранены в [ATtiny13A\Sound\research\shared-speech\bread-noise-refinement.json](../ATtiny13A\Sound\research\shared-speech\bread-noise-refinement.json).

Проверено 714 помещающихся кандидатов; 800 шагов уточнения, seed 23121. Начальный победитель прежней оценки (1022 Б) сохранён в [ATtiny13A/Sound/research/shared-speech/bread-search-model.json](../ATtiny13A/Sound/research/shared-speech/bread-search-model.json). Текущий файл `bread-model.json` содержит выбранную спектральную модель.

| Этап спектрального поиска | Flash, Б | STOI | Log-ошибка спектра | Избыток ВЧ-энергии |
| --- | ---: | ---: | ---: | ---: |
| Первичное уменьшение шума | 998 | 0.708233 | 0.918360 | 0.00200065 |
| Текущий выбранный образ | 1014 | 0.694871 | 0.825994 | 0.00094643 |
| Прежний образ без изменений | 1022 | 0.724265 | 1.050812 | 0.06878833 |

Относительно неизменённого прежнего образа измеренный избыток ВЧ-энергии уменьшился на 98.624%. Это величина конкретной спектральной оценки, не процент воспринимаемого шума и не оценка аналогового выхода.

Меньше спектральная ошибка и измеренный избыток ВЧ, но STOI понизился. Это явный компромисс в пользу спектра и меньшего шума, а не улучшение всех метрик. Неизменённый источник и сравнения для прослушивания находятся в `build/shared-speech/noise-refinement/`: `original.wav`, `previous.wav`, `selected.wav`, `spectrogram.png`.

Исходник длится 2.4000 с; образ — 2.4064 с. Разница — 48 конечных нулевых отсчётов, без обрезки или изменения частоты воспроизведения. Измеренный сдвиг RMS-огибающей прежнего образа: 0.0000 с. Это проверка времени, а не доказательство одинакового субъективного темпа и тембра.

## Файлы полной формы сигнала

Скрипт [tools/build-speech-waveforms.mjs](../tools/build-speech-waveforms.mjs) исполняет сохранённые Flash/EEPROM в AVR-эмуляторе и записывает все отсчёты каждой Tiny-фразы. Это не исходная запись и не повторное сжатие. Манифест [web-player/audio/speech-waveforms/manifest.json](../web-player/audio/speech-waveforms/manifest.json) связывает WAV с точными хешами выбранных образов и PWM.

| Образ | WAV полной фразы | Гц / отсчётов | Генератор |
| --- | --- | --- | --- |
| `hq4-chego-tiny` | [web-player/audio/speech-waveforms/hq4-chego-tiny.wav](../web-player/audio/speech-waveforms/hq4-chego-tiny.wav) | 7500 / 9216 | [tools/build-speech-waveforms.mjs](../tools/build-speech-waveforms.mjs) |
| `hq4-otvechaesh-tiny` | [web-player/audio/speech-waveforms/hq4-otvechaesh-tiny.wav](../web-player/audio/speech-waveforms/hq4-otvechaesh-tiny.wav) | 7500 / 7936 | [tools/build-speech-waveforms.mjs](../tools/build-speech-waveforms.mjs) |
| `hq4-vinni` | [web-player/audio/speech-waveforms/hq4-vinni.wav](../web-player/audio/speech-waveforms/hq4-vinni.wav) | 7500 / 22272 | [tools/build-speech-waveforms.mjs](../tools/build-speech-waveforms.mjs) |
| `hq4-bread-tiny` | [web-player/audio/speech-waveforms/hq4-bread-tiny.wav](../web-player/audio/speech-waveforms/hq4-bread-tiny.wav) | 7500 / 18048 | [tools/build-speech-waveforms.mjs](../tools/build-speech-waveforms.mjs) |

«Вид сигнала» переключает полную форму фразы и текущее окно 85 мс без перезапуска звука. «Сигнал и звук» выбирает PWM до фильтра или выход. Для полной формы Tiny используется тот же ресэмплер и DSP плеера через [web-player/lib/speech-waveform.js](../web-player/lib/speech-waveform.js); LPX использует точные нативные WAV. Во время прослушивания Tiny звук по-прежнему создаёт исполняемая прошивка.

## Воспроизведение результата

Нужны установленные зависимости кодеков Python и нативный C++ компилятор, AVR-GCC проекта; для Nano — simavr observer. Все журналы и промежуточные WAV остаются в `build/`. Пути ниже заменяются на пути установленных инструментов.

```text
python tools/prepare-shared-speech.py --retain
python tools/build-nano-speech-catalog.py --avr-bin /path/to/avr/bin --observer build/nano-lpx/observer/sim_player --lib /path/to/simavr/lib --enable-asm
python tools/build-shared-tiny-speech.py --avr-bin /path/to/avr/bin --proposals 3000 --starts 4 --seed 23120
python tools/refine-shared-tiny-noise.py --avr-bin /path/to/avr/bin --steps 800 --seed 23121
python tools/build-shared-tiny-speech.py --avr-bin /path/to/avr/bin --reuse-search --noise-model build/shared-speech/noise-refinement/model.json --noise-report build/shared-speech/noise-refinement/report.json
node tools/build-speech-waveforms.mjs
python tools/document-speech-assets.py --check
```

Команды выполняются в указанном порядке: сначала заново получается базовая Tiny-модель, затем спектральный поиск и проверяется конечный образ. Первая Tiny-команда временно выбирает победителя прежней оценки; вторая применяет спектральную модель. После изменения выбранного образа WAV полной формы надо пересоздать. Для обновления этой таблицы запустите `python tools/document-speech-assets.py` без `--check`.

На Windows к Nano-команде добавляется `--wsl Ubuntu`. `--reuse-search` у Tiny повторно проверяет уже полученные модели, предварительно сверяя источник и параметры. Первые три Tiny-образа воспроизводит `tools/build-hq4-catalog.py`; их исторический поиск моделей сохранён отдельно. Контрольные суммы исходников в новых рецептах нормализуют текст к LF; HEX и звуковые потоки сохраняют точные байты.
