# Речевые LPX 4/6/8 кбит/с

Исходная ветка `codex/lpx-speech-4-6-8`, база
`b1275514b2d6288411eadf2892c7261f9dcf5246`. Работать только в этом worktree.
Старый цикл ускорения остановлен после round19; это новая работа с потерями.

## План и критерии

- [x] Проверить ветку, чистоту, правила, исходный decoder и round19 evidence.
- [x] Реализовать прототип компактного речевого формата с явным compile-time
  opt-in и отдельной версией. Сохранить v2/v3 и старые 8/12/16 профили.
  Сначала проверить scalar LSF и pitch/sparse excitation без новых таблиц,
  поиска и floating point на MCU. 40 мс: 160 бит при 4 кбит/с, 240 при 6.
- [x] Реализовать offline encoder: LPC analysis, квантование спектра,
  поиск pitch/energy и замкнутый поиск импульсов по фактической integer
  synthesis. Честно зафиксировать ухудшение качества; LPX8 — прежний encoder.
- [x] Проверить независимую модель, native C, truncation, malformed headers,
  повреждённые параметры, частичные хвосты, restart и compile-time rejection.
  Прогнать существующие host-тесты и frozen 91-stream PCM16/PWM regression.
- [ ] Сравнить одинаковые полные записи нескольких голосов: original,
  LPX8/6/4, доступные Opus/Speex. Без gain fitting и обрезки проблемных мест.
  Сохранить SER, max error, STOI, фактический bitrate с заголовком, hashes,
  сведения о delay и split. Codebooks не обучать; held-out training не нужен.
  Аудио и персональные сведения остаются только в ignored build/.
- [ ] Измерить ATmega328P 16 MHz/8 kHz в simavr с активными IRQ:
  queue512/prefill384/unroll9, AVR-GCC7.3 -Os, explicit ASM, local O2,
  v3 mask24; для новых stream — дополнительный speech opt-in. Полное PWM
  equality, wall cycles, Flash с/без stream, static SRAM, stack high-water,
  timing/jitter и underruns. Добавить extra100 IRQ controls и C fallback.
- [ ] Сохранить воспроизводимые инструменты, компактные обезличенные
  результаты, описание формата и measured tradeoffs в AVR cookbook.
  Подготовить локальные WAV для прослушивания и итоговый отчёт с ограничениями.

Каждое логическое изменение — отдельный коммит после локальной проверки
staged content на секреты и личные сведения. Никаких push/upload/publication.
Сравнение качества по waveform и STOI не заменяет субъективное прослушивание;
не выдавать автоматические метрики за человеческие оценки. Simulator-only.

## Журнал

2026-10-26: база и ветка подтверждены, рабочее дерево чистое. UI attachment
не поддерживает этот обычный worktree; все команды используют явный путь.
Изучены v2/v3 parser, integer synthesis, encoder model, AVR harness и round19.
Новые аудио, caches и ELF будут изолированы в build/lpx-speech/.

Прототип v4 реализован: 5/6-bit scalar LSF, 40 ms packet, 20 ms energy/pitch,
2,5 ms sparse pulses, прежний integer synthesis. Общий suite: 104 tests,
один прежний optional skip. Начальные измерения показывают различия между
голосами; итоговые выводы будут по всему набору.

Полный frozen regression заново измерен: 91 AVR image, 2912000 samples,
2495466530 wall cycles (точно round19), PCM16/PWM прежние, underruns=0.
Новый native speech-enabled build тоже совпал со всеми frozen PCM/PWM.
ASan/UBSan: 579054 mutation/reset случаев на 408 входах, без ошибок.
Независимый review: 24 дополнительных random/extreme native/model случая
(seed43288) совпали; уточнено, что неиспользованный padding MCU не проверяет.

Добавлен encoder-only поиск LPX8 из спектров/возбуждения речевого прототипа:
побитовый transcode seed в прежний v2/v3, затем старые rate/joint search.
Приём кандидата требует SSE и STOI не хуже исходного feasible LPX8.
Отдельный native/model transcode тест прошёл. Ограниченный поиск — не
доказательство оптимальности формата; провалы LPX8 будут отражены честно.
