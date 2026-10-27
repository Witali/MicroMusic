# LPX: host proposals и проверка новых данных без роста decoder source

Измерено для ATmega328P / AVR5, GNU ABI, AVR-GCC7.3.0,16MHz/8kHz,
queue512/prefill384/LPC segments2. Приём относится к offline encoder:
существующие decoder fields могут дать полезное дополнительное измерение
поиска без новой MCU-операции. Нового ASM нет; C fallback и отдельные
architecture/ASM-enable и hardware Flash selectors сохраняются.

## Расширять узкий proposal interval с проверенным откатом

Скалярная оценка residual energy предлагает несколько scale codes, но не
доказывает оптимальность этого интервала после integer synthesis. В profile4
обязательный импульс±8 при ненулевом scale создавал ошибку даже на exact
digital silence. Дополнительные center−4/center−6/zero probes находят нулевой
масштаб, доступный в прежнем формате. Для других голосов полезен второй
общий preset — pre-emphasis0.75 в существующем Q14 header field.

Оба предложения рассчитываются на ПК и декодируются при исходном уровне.
Не считать изменение scale точным умножением waveform: integer rounding,
pitch history, LPC state, saturation и PWM quantization нелинейны. Сравнивать
полные PCM16 и фактические PWM SSE/STOI, затем повторно проверять joined
выход после независимых segment resets. Per-segment STOI floors не доказывают
whole-case floor. При отказе оставлять точные прежние bytes и исходный cap.

В v5-корпусе181 уникальный PCM case /306 segments /362 profile pairs
изменились15 outputs,347 остались точными. PCM SSE улучшен во всех15,
PWM SSE в14; доступный STOI не ухудшается. Digital silence4:
PCM SSE3406008→0,1553→1414B. Общие files2027293→2026980B;
некоторые отдельные файлы растут внутри прежнего cap. Это same-cap,
не equal-achieved-bitrate и не isolated host-speed comparison.

## Новый corpus требует новых actual-output checks

Совпадение decoder source не доказывает время на новом потоке. Реальные
AVR ELF checked612 compact-only jobs по всему корпусу и132 common jobs
по речи/regression/phrases. Все полезные PWM bytes точны, underruns=0.
Прежний small-code recipe unroll1/tuning0/Os/LTO/mcall-prologues/mrelax
сохраняет полный externally observed harness ABI и exact audio exclusion.

Program Flash без stream, включая startup/harness/tables:5909–5912B
compact-only и7889–8032B common. SRAM1085/1105B. Observed ready-phase
stack max105/124B, minimum margin858/819B. Разброс emitted size при разных
ROM arrays/relaxation не означает новый decoder source. Не вычитать код
из raw ELF и не удалять profiler, чтобы получить мнимую экономию.

Самый тяжёлый measured source каждого mode/profile даёт новые64k-sample
continuous controls. Повторять stored packet fields с непрерывным состоянием,
а не декодированные WAV; disclose unused partial-packet tail и заново
рассчитывать model oracle. Все8 ASM normal/+100IRQ controls без пропусков.
Все4 C controls сохраняют полезные значения, но дают43237–45082 underruns:
их real-time support не заявляется. Physical hardware и startup/worst-case
stack не измерены. Включение ASM остаётся явным на настоящем AVR5 target.

## Не смешивать correctness и качество

206 host tests:205 pass,1 optional skip. Строгие waveform/activity checks
прошли141/362 outputs,221 остался diagnostics, главным образом из-за тихих
окон fixed8-bit PWM. Это не parser/timing failures. У6 может быть ниже SSE,
но больше muted windows: шумный4 output тоже может быть ненулевым.
Peak error вырос в5 PCM/6 PWM points, его монотонность не обещалась.
Short-STOI unavailable не должен становиться фиктивным floor1e-5.

Это исходная проектная комбинация existing-format proposals и corpus
admission checks. Нет trained codebooks, нового vendor code или регистров.
[Code/recipe](../../Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/SHARED_CORPUS.md),
[полные измерения, hashes и ограничения](../../Codecs/LPX/research/shared-corpus-2026-10-27/README.md).
