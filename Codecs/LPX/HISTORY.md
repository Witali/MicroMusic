# Коммиты импорта LPX

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
