# История LPX: импорт и продолжение разработки

Исходный архив содержит самостоятельные снимки этапов и восстановленный
технический журнал. Исходных Git-объектов, авторов и точных дат коммитов
в нём нет. Ниже перечислены новые коммиты импорта от 25.10.2026; даты
разработки 22–25 октября взяты из сохранённых отчётов. История не была
искусственно датирована прошлым.

| Коммит | Сохранённый этап |
| --- | --- |
| `6a2b0e2e` | Import historical LPC2 Arduino foundation |
| `f97006fb` | Import original LPX3 encoder and reference decoders |
| `a4b6fb1d` | Preserve initial LPX3 AVR port and VBR research |
| `9eee6f06` | Preserve LPX3 Rice v5 footprint optimization |
| `ce8019a0` | Preserve LPX3 Rice v6 repeated-mode encoding |
| `3bec16b5` | Preserve LPX3 Rice v7 compact encoding research |
| `48067578` | Preserve initial LPX4 hybrid decoder and packing tools |
| `ea769ebf` | Preserve LPX4 CELP budget encoder milestone |
| `fdc7f8d7` | Preserve experimental LPX4 Q1 precision branch |
| `22a50b80` | Preserve LPX4 desktop batch encoder acceleration |
| `5e48b3e3` | Import active LPX4 Q0 encoder and decoder |
| `73326a9f` | Preserve LPX codec benchmark reports and synthetic audio |
| `61fa216e` | Record unfinished universal WAV encoder status |
| `1d0dbb40` | Preserve LPX development journal and archive provenance |

Каждый этап сохранён отдельным автономным каталогом. Порядок импорта
передаёт техническую последовательность LPC2 → LPX3 → AVR/VBR → Rice
v5/v6/v7 → LPX4 Hybrid → CELP → Q1 → Batch → актуальный Q0. Q1 и Batch
сохранены как отдельные экспериментальные ветки; они не объявлены
автоматически включёнными в Q0.

Подробности разработки: [исходный журнал](00_READ_FIRST/HISTORY_FULL_RU.md),
[отчёты](00_READ_FIRST/OLD_REPORTS/),
[точный перечень файлов архива и исключений](IMPORT_MANIFEST.json).
Следующие коммиты интеграции документируют происхождение общих синтетических
фикстур и добавляют навигацию с результатами новой проверки.

## Продолжение плана 25.10.2026

| Коммит | Изменение |
| --- | --- |
| `df2b28a` | Самостоятельный WAV→LPX4, автоматический LPC/LSF, целочисленный closed loop и сегменты |
| `d134d18` | Beam 1/4/8/16 и чередование LSF/возбуждения/Q14 с сохранением размера и качества |
| `bb75a4a` | Отбрасывание неустойчивых Q12 фильтров и дополнительные старты анализа |
| `bc607e4` | Полный AVR ELF/HEX, Timer1/Timer2/IRQ и независимый simavr-профиль с очередью и PWM parity |
| `8e3e564` | Воспроизводимый корпусный прогон и сравнение LPX3/LPX4/Opus/AAC по фактическим byte caps |

Исходное C++-ядро Q0 сохранено. [Отчёт с измерениями и оставшимися пунктами](research/q0-encoder-2026-10-25/README.md).
