# Компактная упаковка и качество речи

База: `b87ca265`, существующие branch/worktree `codex/lpx-speech-4-6-8`.
Исходные v4 и WAV из build/lpx-speech/comparison/ сохраняются неизменными.
Новые данные и audio только в ignored build/lpx-speech-compact/.

- [x] Проверить состояние, формат и предыдущие измерения.
- [x] Измерить избыточность LSF/energy/pitch/pulses на тех же четырёх голосах.
- [x] Реализовать явно включаемый v5: точные LSF gap/temporal Rice, radix20
  для пар позиций LPX6, без обучения и таблиц большого размера. Сравнить
  полные параметры и PCM/PWM с v4; считать полный размер с новым header.
- [x] Проверить улучшение качества при неизменных спектральных коэффициентах:
  encoder-only уточнение и необязательные дополнительные импульсы за счёт
  экономии. Ограничить полный файл прежним бюджетом 4/6 кбит/с с headers;
  принимать только кандидаты с сохранением полных SSE и STOI floors.
- [ ] Native/model, malformed/truncation/restart, старые форматы, C fallback,
  ASan/UBSan. Проверить полные PWM и active-IRQ timing в simavr для принятых
  результатов, +100 IRQ, 8-second continuous controls. Измерить Flash,
  static SRAM и наблюдаемый stack, включая цену нового parser.
- [ ] Подготовить новые локальные WAV/HTML сравнения, обезличенный отчёт,
  cookbook и отдельные проверенные коммиты. Не публиковать audio или secrets.

Ни меньший поток, ни лучшие waveform metrics не считаются доказательством
лучшего субъективного качества или более быстрого MCU. Старые профили и
явно выбираемый portable C backend сохраняются. Новая ASM не планируется.

## Журнал

Пользователь сообщил, что речь достаточно разборчива, и предложил экономить
данные упаковкой тех же коэффициентов. Начат отдельный этап: exact packing
отделён от изменений возбуждения, чтобы оценивать оба эффекта честно.
Делегированы независимый анализ распределений и encoder-only refinement;
основной агент отвечает за формат, decoder, AVR и итоговую интеграцию.

V5 реализован с отдельным compile-time enable,22-byte header и длиной
payload. Чистая упаковка сохраняет все параметры и полный PCM/PWM. Режим
extras включает маркеры только при соответствующем global flag; столкновения
импульсов складываются перед q saturation. По независимому review усилена
проверка trailing data полных пакетов и коротких входов profiler.

Окончательный host suite:119 tests (118 passed,1 optional hard-link skip).
ASan/UBSan:605670 mutation/reset случаев,456 inputs, ошибок нет. Есть все
400 radix20 values, insertion/collision, partial tails, restart/snapshots,
проверки feature flags и старых конфигураций memory/history. AVR matrix
на окончательном decoder выполняется отдельно; прежний speed loop не открыт.

Encoder-only refinement готов: horizon160/pass1, затем horizon320/pass2,
full-waveform acceptance по640-sample groups. Все8 вариантов улучшили
SSE/STOI при прежних v4 header/размере/спектре. Дополнительный v5 search
оставляет spectrum/params/base pulses неизменными и добавляет импульсы
только после полной SSE/STOI проверки. Ограничение128 full evaluations
на поток достигнуто; часть битового бюджета намеренно не использована.
Итоговые кандидаты:4k SER7,00→7,75/STOI0,751→0,783 при1850..1908B
вместо2020B;6k SER9,24→9,92/STOI0,792→0,812 при2618..2699B вместо3020B.
