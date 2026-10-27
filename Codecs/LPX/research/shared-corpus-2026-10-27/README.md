# LPX 4/6 на общем звуковом корпусе, 27.10.2026

Проверены рекомендуемые речевые профили **v5 4/6**, включая работу с новым
локальным корпусом и компактной прошивкой. 181 уникальный PCM-вход дал
362 пары baseline/selected и 612 сегментных потоков. Все они декодируются
точно через native C, compact-only C, независимую integer model и AVR ASM.
Это проверка указанных профилей; прежние 8/12/16 на всём этом расширенном
наборе заново не кодировались.

Ограниченный PC-поиск улучшил SSE в **15 вариантах: 9 для профиля4 и 6 для6**.
Во всех 362 парах сохранены полные PCM/PWM SSE/STOI floors и прежние byte
caps; остальные 347 выходов побитово прежние. Декодер, его арифметика и формат
не изменялись. Поиск выбирает параметры при кодировании конкретной записи,
а не использует заранее обученную таблицу голосов.

Успешное декодирование и хорошее качество различаются. Строгий набор
waveform/activity проверок прошли **141/362** выходов; **221** сохранён как
quality diagnostics. Главная причина — тихие окна, теряемые при фиксированном
8-bit PWM, особенно в затухании инструментальных нот. Это не 221 parser error
или underrun. Физическая плата и субъективная разборчивость не измерялись.

## Корпус и неизменность входов

Из общей коллекции выбраны 182 исходных файла; после exact-PCM dedup остался
181 вход. Alternate-rate copies и готовые Speex/oracle streams не выдаются за
новые сигналы. В проверке 15 188 029 исходных отсчётов, **31 мин 38,504 с**.

| Cohort | Полные записи | Сегменты ≤64000 samples |
|---|---:|---:|
| RU/EN natural, quiet −24 dB, noise15 dB | 20 | 22 |
| Прежние speech/music/synthetic regression | 27 | 27 |
| Независимая речь | 4 | 10 |
| Подготовленные короткие фразы | 5 | 7 |
| Полные музыкальные оригиналы | 3 | 118 |
| Отдельные инструментальные ноты | 122 | 122 |
| Всего | 181 | 306 |

Проверены source/index hashes, PCM16 hashes и непрерывное покрытие каждого
полного входа сегментами. Длинные оригиналы не обрезались: например,
фортепианная запись длится около473 с. Сегменты сбалансированы, чтобы не
создавать хвост из нескольких десятков samples. Состояние декодера между
ними сбрасывается; joined metrics включают последствия этих границ.

Входы приведены к mono PCM16/8kHz: среднее каналов, rational resampling при
необходимости, одно округление/clamp. Громкость и DC не подгонялись.
Два samples независимой речи потребовали clipping после resampling; это
сохранено в conversion metadata. Готовые cartoon WAV уже имели upstream
обработку, она маркируется и повторно не применяется. Media, source names,
credits и private provenance остаются локально в ignored build.

## Что улучшено

Baseline соответствует прежнему выбранному рецепту: v4 encode,
`refine(passes=2, horizon=320)`, затем compact extra innovations. Полный cap
сегмента: `20 + ceil(n/320) * 20` для4 либо `*30` для6. V5 header22 входит
в этот cap. Номинальный профиль и достигнутый битрейт не тождественны:
учитываются все заголовки, padding последнего пакета и независимые resets.

Новый `optimize_speech_v5` пробует максимум два общих host-предложения:
предыскажение0.75 в существующем header и дополнительные низкие/нулевые
масштабы, которые исключал узкий energy-based interval. Первый вариант
заново анализирует спектр, второй сохраняет его. Это новый параметрический
поиск, а не продолжение прежнего утверждения о frozen spectra.

Default corpus policy `necessary` запустила поиск на39 case/profile points.
Quiet/noisy labels, waveform/level problems и фиксированные диагностические
пороги выбирают объём offline работы. Они не ослабляют acceptance floors.
Другие музыка и синтетика сохраняют baseline; exact zero независимо от
cohort может получить только low/zero-scale repair. Есть явный `all-speech`.

Кандидат обязан соблюдать cap, полные PCM16 и фактические PWM SSE/STOI
floors, затем пройти отдельную проверку joined записи и не добавить новую
activity failure. Иначе сохраняются исходные байты. На этом наборе whole-case
rollback не потребовался; отвергнутые локальные proposals учтены явно.

| Результат | Профиль4 | Профиль6 |
|---|---:|---:|
| Case/profile points | 181 | 181 |
| Изменены с уменьшением PCM SSE | 9 | 6 |
| Уменьшился также PWM SSE | 8 | 6 |
| Суммарные file bytes ранее | 822868 | 1204425 |
| Теперь | 822765 | 1204215 |

Всего сэкономлено313 байт. Некоторые отдельные файлы выросли внутри
прежнего cap, поэтому сравнение относится к **одинаковому потолку**, а не
к одинаковому достигнутому размеру каждого файла. Дополнительный поиск
тратит PC-время; изолированное ускорение encoder здесь не заявляется.

Для20 полных RU/EN записей средний SER изменился6,923→7,048 dB для4
и9,038→9,102 dB для6; средний STOI0,76038→0,76159 и0,79457→0,79543.
Один тихий RU вход4: SER5,893→6,894 dB, STOI0,64193→0,64897;
его6:8,979→9,813 dB, STOI0,70146→0,71340. Эти два выхода всё ещё
помечены PWM activity diagnostics; улучшение метрики не скрывает проблему.

У digital silence4 узкий поиск давал PCM SSE3406008. Zero-scale proposal
дал точный ноль и уменьшил файл1553→1414 байт. PWM и раньше был нулевым:
исправлен внутренний PCM и лишние данные, а не найден слышимый PWM-шум.

## Границы качества и метрик

- После выбора остаются4 PCM activity diagnostics (instrument cases),
  219 PWM activity diagnostics,4 случая PCM SSE хуже silence и6 PWM SSE
  хуже silence. Причины пересекаются, поэтому их числа не складываются.
- Два quiet-English4 points и synthetic DC-like signal в обоих профилях
  остаются хуже silent reconstruction по PCM SSE. Cap не увеличивался.
  Это результат конечного поиска, не доказательство невозможности формата.
- Activity detector использует относительный порог−30 dB и30 ms runs.
  Он замечает потерянные тихие детали, но сам по себе не оценивает качество:
  шумный выход также может оставаться ненулевым. Поэтому показатели PCM,
  PWM, SSE/STOI и activity сохраняются раздельно. У6 может быть больше
  помеченных тихих окон при меньшем общем SSE, чем у4.
- Peak error не ограничивался монотонным floor: он вырос в5 PCM и6 PWM
  points, несмотря на соблюдение SSE/STOI. Число clipped outputs не выросло.
- STOI при недостатке active STFT frames теперь `null`, а не числовая
  заглушка1e-5. Слишком короткие входы отсекаются по точной framing bound
  установленной pystoi до её AxisError. Реальные низкие scores сохраняются.
- Средние по cohorts и худшие отдельные записи приведены отдельно. Один
  synthetic failure сильно портит общий energy-weighted SER; его нельзя
  выдавать за характерный score речи или скрывать в среднем.

Музыка/ноты здесь проверяют границы речевого low-rate профиля. Утверждение
об универсальном музыкальном качестве4/6 из этих данных не следует. Новых
человеческих оценок прослушивания и analog PWM measurements нет.

## AVR: корректность, Flash и время

ATmega328P / AVR5, AVR-GCC7.3.0, simavr1.6,16MHz/8kHz,
queue512/prefill384, LPC segments2. Рецепт прежний:
unroll1/tuning0, `-Os -flto -mcall-prologues -mrelax`, явный ASM-enable.
Hardware Flash access и выбор arithmetic backend независимы; portable C
доступен на самом AVR. Новый ручной ASM и hardware definitions не добавлены.

| Сборка | Normal simulations | Полезных samples | Program Flash без audio | Static SRAM | Underruns |
|---|---:|---:|---:|---:|---:|
| Compact-only, все181 inputs | 612 | 30376058 | 5909–5912 B | 1085 B | 0 |
| Common, речь/regression/phrases | 132 | 5712592 | 7889–8032 B | 1105 B | 0 |

Оба профиля совпали с полным сохранённым PWM; `decoder_error=0`.
Common scope —56 inputs и66 сегментов в двух rates; длинная музыка и
instrument notes проверены на AVR в compact-only, не объявлены заново
измеренными в common. Counts обозначают stream jobs, а не независимых людей.

Flash = `.text + .data − exact embedded stream bytes`; startup, tables и
прежняя profiling/playback обвязка остаются. Это не raw ELF и не isolated
library size. LTO/relaxation/ROM-array placement дают несколько байт разброса
между образами при прежних исходниках. Наличие exact массива и profiling ABI
проверяется, а не предполагается. Полное сравнение core hashes с прошлым
Flash этапом подтверждает отсутствие source changes.

Наблюдаемый stack после ready:90–105B, margin858–873B для compact-only;
109–124B, margin819–834B для common. Это не startup/worst-case proof.
Weighted wall cycles/sample778,875/844,845 относятся к разным scope,
включают IRQ и instrument stores; сравнение не является speedup experiment.

Для каждого mode/profile выбран source с максимальным измеренным средним.
Его полные stored packet fields повторены до64000 samples с непрерывным
состоянием. Ранее не проигранный partial-packet tail маркируется. Эталон —
свежая integer model, а не склейка WAV. Все8 normal/+100IRQ ASM controls
дали точный PWM и0 underruns.

| Mode | Control | Cycles/sample4 /6 | Underruns4 /6 |
|---|---|---:|---:|
| Compact-only | ASM normal | 797,533 /799,462 | 0 /0 |
| Compact-only | ASM +100IRQ | 808,627 /812,002 | 0 /0 |
| Compact-only | C fallback | 3189,100 /3180,578 | 43519 /43237 |
| Common | ASM normal | 861,551 /858,817 | 0 /0 |
| Common | ASM +100IRQ | 876,203 /871,522 | 0 /0 |
| Common | C fallback | 3232,926 /3223,631 | 45082 /44782 |

C fallback сохраняет полезные значения, но не выдерживает deadline на этом
стенде; пропуски не удалены из timing conclusion. Поддержка real-time
ограничена измеренными ASM configurations. Физическая плата не проверена.
Прежние exhaustive math/r1 и malformed-input результаты относятся к прежним
source-identical core/math; новые такие exhaustive runs не заявляются.

## Проверки, данные и воспроизведение

Полный suite: **206 tests,205 passed,1 optional hard-link skip**,92,145s.
Дополнены short-STOI bounds, настоящий длинный STOI enhancement fixture,
source conversion/dedup, cache tamper/partial tails, guarded proposals,
joined rollback и AVR accounting. Краткие Windows read locks при atomic
JSON replace получили bounded retry; численные данные от этого не меняются.

[Команды и интерпретация статусов](../../01_ACTIVE_Q0_CODEC/tools/SHARED_CORPUS.md),
[план](../../SHARED_CORPUS_PLAN_RU.md),
[cookbook](../../../../docs/avr-asm-cookbook/lpx-shared-corpus.md).
Локальные playlists original/baseline4/selected4/selected6/PWM4 находятся
в ignored `build/lpx-corpus-2026-10-27/listening/`;131952 samples,16,494s,
два unchanged-level входа с0,5s gap. В Git аудио не добавляется.

- [Сводка и тесты](summary.json), [cohort/language/condition/split groups](groups.json),
  [все362 пары и сегменты](paired.json), [proposals и diagnostics](optimization.json).
- [Анонимные входы/геометрия/hashes](inputs.json),
  [source/package fingerprints и decoder equivalence](environment.json).
- [AVR summary](avr-summary.json), [compact-only612](avr-compact-only.json),
  [common132](avr-common.json), [12 continuous controls](avr-stress.json).

В AVR JSON одинаковые поля вынесены в shared fields/pools; схема описывает
точное восстановление каждой строки. Retention проверяет реальные
ELF/HEX/bin/PWM hashes и связь с выбранным output, но не копирует эти файлы,
исходный звук, private manifests или raw logs в публикуемые данные.
