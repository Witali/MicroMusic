# LPX 4/6: проверка на общей звуковой коллекции

База: main `7c6edee7`, 27.10.2026. Продолжение речевых v5/Flash этапов.
Работа идёт в прежнем worktree после fast-forward к актуальной main.

- [x] Найти общую локальную коллекцию, проверить manifests/hashes и отделить
  входные записи от готовых codec streams/oracles и повторных sample rates.
- [x] Подготовить все подходящие записи при исходной громкости: 182 inputs,
  181 уникальный PCM case, 306 balanced segments <=64000 samples. Сохранить
  каждый отсчёт; отдельные fingerprints полного WAV и сегментов.
- [x] Прогнать оба рекомендуемых v5 профиля 4/6: 362 case/profile points,
  612 сегментных потоков. Recipe: v4 encode, refine2/horizon320, compact
  extras при исходном полном file cap. Проверять native/model/compact-only,
  точный PWM transfer, реальный bitrate, ошибки и качество по каждой записи.
- [x] Измерить дефекты тихой/новой речи. Принять лишь ограниченные общие
  host proposals с откатом, прежним cap и PCM/PWM SSE/STOI floors; не
  поднимать бюджет автоматически и не скрывать no_fit средними оценками.
- [x] Проверить выбранные новые потоки в AVR simavr с активными IRQ;
  continuous normal/+100 IRQ и C fallback controls. Источник firmware
  должен совпадать с измеренным; не объявлять физическую плату проверенной.
- [x] Сохранить обезличенные результаты, условия/пределы и воспроизведение;
  завершить focused local commits после staged privacy inspection.

Исходники и звук коллекции не публикуются. Media, source provenance,
выходы decoder, ELF/HEX и промежуточные caches остаются в ignored build.
Заранее подготовленные cartoon WAV уже имеют upstream gain/DC processing;
этот факт маркируется, повторной нормализации здесь нет. Два отсчёта
независимой речи потребовали PCM16 clipping после resampling; счётчик сохранён.
STOI при недостатке активных кадров недоступен, а не равен заглушке 1e-5.
Музыка и instrument notes — отдельные cohorts; они не становятся речевыми
дикторами и не расширяют область речевого quality claim.

## Проверенные промежуточные результаты

Все 362 пары baseline/selected и 612 потоков прошли native common C,
compact-only C, independent model и PWM transfer проверки. Улучшены
15 case/profile points (9 в профиле4,6 в профиле6); остальные сохранены
побитово. Все полные PCM/PWM SSE/STOI floors соблюдены, общий byte cap
не увеличен; суммарные файлы стали на313 байт меньше. Новая спектральная
переоценка pre0.75 явно отличается от прежнего frozen-spectrum этапа.

Цифровая тишина profile4:1553→1414 байт, PCM SSE3406008→0;
PWM уже был точным нулём. Неприемлемые при текущих waveform/activity
проверках случаи сохранены как diagnostics, а не объявлены подходящими
из-за успешного parsing. Ограничение тихих деталей8-bit PWM учитывается
отдельно от внутреннего PCM16.

Полный suite206:205 passed,1 optional hard-link skip,92.145s.
STOI теперь недоступен при недостатке реальных кадров; старый80ms тест
заменён достаточным6400-sample fixture. Перезапись JSON при кратких
Windows read locks получила bounded retry, без изменения численных данных.
Исходники C++ декодера, integer math и его Flash recipe не менялись.

## Завершение

Сохранён [отчёт и10 JSON evidence files](research/shared-corpus-2026-10-27/README.md).
612 compact-only и132 common normal AVR jobs: все полезные PWM точны,
errors/underruns=0. Ещё12 continuous controls:8 ASM normal/+100IRQ
без пропусков,4 C exact по полезным значениям, но non-realtime.
Program Flash5909–5912/7889–8032B без audio, SRAM1085/1105B.
Common132 охватывает речь/regression/phrases; instrument/fullmusic
не объявлены заново измеренными в common. Physical board не измерена.
Отдельные rawmedia/privateprovenance/ELF/HEX/logs остаются ignored.
