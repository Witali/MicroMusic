# Эксперименты NB3

## Четыре long-pitch вектора одним вызовом — сравнение вариантов

База `8fd8229`, пути относительно `Codecs/Speex/AVR/`. Авторские AVR GNU ABI
прототипы сохраняют Xiph fixed-point math и отдельный C fallback; исходные
notices и `vendor/speex-1.2.1/COPYING` базы остаются. Параметры — четыре RAM
индекса 0..31, три signed8 gain с L1<=147, 42 завершённых signed16 history
слова, scale 0..121000000. Выход — 40 сэмплов; таблица shapes в Flash.

Сохранены три непринятые стадии:

- `long40.patch`: один машинный scaling/clamp body для всех входов, r9
  различает продолжение следующего вектора и обычный возврат. Старые непустые
  вызовы платят ещё 7 тактов на ABI-вход/выход.
- `long40-direct.patch`: собственный 40-сэмпловый цикл без mode-dispatch,
  четыре индекса на стеке, gains/history сохраняются между векторами.
- `long40-shared-flow.patch`: первый вариант с rolling-dot fallthrough в
  transform и более коротким хвостом цикла для частого T=1 пути.

Все три точны на полном корпусе 31 поток / 9 100 кадров. Их собственных
component/PWM admission не было. Принятый вариант сочетает отдельный цикл
с перестановкой старого rolling-loop; его арифметика теперь ведётся в общих
GAS-макросах `src/innovation_core.inc`. Это общий исходный текст с двумя
машинными телами, без дополнительных вызовов на каждый сэмпл.
Его полные проверки — `long40-unit.json`, `long40-admission-audit.json`.

В новой игнорируемой копии pinned базы применить один patch и собрать ASM
(Python 3.12+, Git, AVR GCC/Node и oracle из README кодека):

```powershell
python -c "from pathlib import Path; import io, subprocess, tarfile; d=Path('Codecs/Speex/AVR/build/long40-example'); d.mkdir(); data=subprocess.check_output(['git','archive','8fd8229:Codecs/Speex/AVR','src','tools','tests','vendor','handoff','reference']); tarfile.open(fileobj=io.BytesIO(data)).extractall(d,filter='data')"
git apply --ignore-space-change --directory=Codecs/Speex/AVR/build/long40-example docs/avr-asm-cookbook/examples/long40.patch
python Codecs/Speex/AVR/build/long40-example/tools/build.py --avr-gcc avr-gcc --backend asm
node Codecs/Speex/AVR/tests/verify_avr.mjs --backend asm --verify-reset --firmware Codecs/Speex/AVR/build/long40-example/build/profile --oracle Codecs/Speex/AVR/build/reference --out Codecs/Speex/AVR/build/long40-example/fixtures
```

Для следующих стадий заменить имя patch. Применимость всех трёх проверена
`git apply --check`. Сравнение Flash/среднего/максимума, SHA-256 и полный
corpus каждого варианта сохранены в `reports/long40-variant-decision.json`
папки кодека. Другие MCU и физическая плата не измерены.

## Общая обработка сэмпла C — отклонённые эксперименты

`nb3-shared-finish.patch` и `nb3-shared-shape-finish.patch`, база `a4c3b39`,
пути относительно `Codecs/Speex/AVR/`. Первый выносит adaptive-clamp,
сложение innovation и Q14 saturation в одну `noinline/noclone` C-подпрограмму
для long/short pitch. Второй включает в неё и масштабирование shape.
Авторские C-прототипы сохраняют точные floors, modulo-32 и Xiph BSD notices.
Для AVR helper собирается O2; C backend выбран явно.

На 88 fixture-кадрах ATmega328P / AVR GCC 7.3 mixed Os/O2/O3+LTO:

| Вариант | Decoder Flash | Среднее время относительно базы | Peak stack |
| --- | ---: | ---: | ---: |
| Исходный C | 12 308 Б | база | 153 Б |
| Общий finish | 12 022 Б | +2,0863% | 153 Б |
| Общий shape + finish | 11 784 Б | +3,2449% | 153 Б |

Оба точны на этих кадрах, static SRAM 1 119 Б. Кандидаты остановлены по
скорости после короткого отбора; полного corpus/component/PWM admission
не было. Эти результаты не относятся к другим MCU или компиляторам.
В production оставлена обработка сэмплов внутри циклов; там объединены
прологи/эпилоги функций (см. основной cookbook).

В новой игнорируемой копии pinned базы применить **один** patch и собрать C
(Python 3.12+, Git, AVR GCC/Node и oracle из README кодека):

```powershell
python -c "from pathlib import Path; import io, subprocess, tarfile; d=Path('Codecs/Speex/AVR/build/shared-finish-example'); d.mkdir(); data=subprocess.check_output(['git','archive','a4c3b39:Codecs/Speex/AVR','src','tools','tests','vendor','handoff','reference']); tarfile.open(fileobj=io.BytesIO(data)).extractall(d,filter='data')"
git apply --ignore-space-change --directory=Codecs/Speex/AVR/build/shared-finish-example docs/avr-asm-cookbook/examples/nb3-shared-finish.patch
python Codecs/Speex/AVR/build/shared-finish-example/tools/build.py --avr-gcc avr-gcc --backend c
node Codecs/Speex/AVR/tests/verify_avr.mjs --backend c --frames 8 --firmware Codecs/Speex/AVR/build/shared-finish-example/build/profile --oracle Codecs/Speex/AVR/build/reference --out Codecs/Speex/AVR/build/shared-finish-example/smoke
```

Для второго заменить имя patch. `git apply --check` проверен для обоих.
Измеренные binary SHA-256 и точная область проверки сохранены в
`Codecs/Speex/AVR/reports/shared-routines-variant-decision.json` и `*-smoke.json`.

## Исторический long-pitch fusion

`nb3-long-pitch-fusion.patch` — исходный C-прототип для ATmega328P / AVR GCC
7.3.0, база `30779f0`. Авторская переработка текущего restricted Xiph NB3;
исходные BSD-уведомления и лицензия `vendor/speex-1.2.1/COPYING` сохраняются.
Патч сохраняет отдельный ранний C-прототип. В основном декодере он заменён
общим ASM-ядром и C fallback; этот исторический вариант сам по себе не проходил
PWM/ISR-gate. Не применять его поверх текущей реализации. Native Clang
24.0.0git проверен на точность C; он игнорирует GCC `optimize("O2")`.

Из корня task worktree, после подготовки обычного reference/oracle и toolchain
из README кодека, создать **новую** игнорируемую копию и применить патч там:

```powershell
python -c "from pathlib import Path; import shutil; r=Path('Codecs/Speex/AVR'); d=r/'build/fused-pitch-example'; d.mkdir(); [shutil.copytree(r/n,d/n) for n in ['src','tools','tests','vendor','handoff','reference']]"
python -c "from pathlib import Path; import subprocess; r=Path('Codecs/Speex/AVR/build/fused-pitch-example'); [(r/n).write_bytes(subprocess.check_output(['git','show','30779f0:Codecs/Speex/AVR/'+n])) for n in ['src/nb_decode.c.inc','src/pitch24.h']]"
git apply --ignore-space-change --directory=Codecs/Speex/AVR/build/fused-pitch-example docs/avr-asm-cookbook/examples/nb3-long-pitch-fusion.patch
python Codecs/Speex/AVR/build/fused-pitch-example/tools/build.py --avr-gcc avr-gcc --backend c
node Codecs/Speex/AVR/tests/verify_avr.mjs --backend c --verify-reset --firmware Codecs/Speex/AVR/build/fused-pitch-example/build/profile --oracle Codecs/Speex/AVR/build/reference --out Codecs/Speex/AVR/build/fused-pitch-example/fixtures
```

`--ignore-space-change` допускает LF/CRLF в исходной Windows-копии. Патч
воспроизведён на чистой копии: binary SHA-256
`b9cc79536ad70c9b33b57356d7fdea5c4171ea9e34145c1fccaec7bec118658d` совпал
с проверенными 13 254 AVR-кадрами. 31 native поток/9 100 кадров также точен,
с проверкой invalid calls и scratch_peak=140. Все отчёты, размеры и сравнение
вариантов сохранены в `Codecs/Speex/AVR/reports/long-pitch-experiment-*.json`.

Условие pitch>=41 гарантирует, что последний tap читает не новее exc[-1].
Отдельная ветка short pitch сохраняет все повторы и нулевые хвосты. Буфер
120 Б пока остаётся для неё; RAM-экономия этому эксперименту не приписывается.
Эти измерения описывают исходный эксперимент. Последующие реализации
описаны в отчётах `fused-long-*`, `segment-*` и основном cookbook.

## Исторический direct short-pitch C — не принят

`nb3-short-pitch-direct.patch`, база `f99424c`, считает три tap напрямую.
Для `j-pitch-1+tap>=0` вычитается ещё pitch; оставшийся неотрицательный
индекс означает нулевой хвост. Каждый прочитанный индекс отрицателен:
готовое возбуждение можно записывать сразу. Сохранены clamp, Q14 и задержка.
Код — авторская переработка restricted Xiph NB3 с прежней BSD-лицензией.

AVR GCC 7.3.0 mixed Os/O2/O3+LTO, ATmega328P, 31 поток: среднее -0,2238%,
human speech -0,2434%, corpus max 269 656→266 183, coverage max
270 221→267 238 тактов; Flash +46 Б, RAM/стек прежние. Есть регрессии:
худшее среднее потока +0,0777%, hard_clipped max +1 840 тактов. Pitch-buffer
120 Б ещё выделяется. Точны 13 254 AVR и 9 100 native кадров; на host включены
scratch bounds и API-проверки. Независимые full-scale segment/tail tests и
PWM/ISR-gate этого прототипа не выполнялись. Он заменён диапазонным ASM/C
методом из `short_pitch.h`; его проверки — `segment-*`. Другие MCU не измерены.

В новой игнорируемой папке воспроизвести **только C backend** из pinned базы
(Python 3.12+, Git, AVR/Node tools из README кодека):

```powershell
python -c "from pathlib import Path; import io, subprocess, tarfile; d=Path('Codecs/Speex/AVR/build/short-pitch-example'); d.mkdir(); data=subprocess.check_output(['git','archive','f99424c:Codecs/Speex/AVR','src','tools','tests','vendor','handoff','reference']); tarfile.open(fileobj=io.BytesIO(data)).extractall(d,filter='data')"
git apply --ignore-space-change --directory=Codecs/Speex/AVR/build/short-pitch-example docs/avr-asm-cookbook/examples/nb3-short-pitch-direct.patch
python Codecs/Speex/AVR/build/short-pitch-example/tools/build.py --avr-gcc avr-gcc --backend c
node Codecs/Speex/AVR/tests/verify_avr.mjs --backend c --verify-reset --firmware Codecs/Speex/AVR/build/short-pitch-example/build/profile --oracle Codecs/Speex/AVR/build/reference --out Codecs/Speex/AVR/build/short-pitch-example/fixtures
```

Полные замеры: `Codecs/Speex/AVR/reports/short-pitch-experiment-*.json`.

## Побайтовый C MAC — отклонённый эксперимент

`nb3-c-byte-mac.patch`, база `d000fc4`, пути относительно `Codecs/Speex/AVR/`.
Авторский C-прототип заменяет signed16 × signed16 на четыре signed/unsigned
8-битных произведения и uint32-суммирование modulo 2³². Все промежуточные
произведения помещаются в 16 бит; перед сдвигами выполняется приведение к
uint32. ASM явно отключён, аппаратные PROGMEM-чтения остаются отдельными.
Xiph BSD-лицензия и остальные notices базы сохраняются.

На ATmega328P / AVR GCC 7.3 mixed Os/O3, LTO, fwrapv результат **хуже**:
отдельный MAC 119 против 69..73 тактов, декодер +34,3396% среднего времени
31 потока, Flash 11 836→13 400 Б, SRAM/stack прежние. Точны 1 310 720 пар
каждого MAC, все первые s16 operands × 16 граничных вторых, ещё 262 144
случайных пар, произвольный uint32 accumulator, ABI/r1/read-only inputs.
Все 9 100 кадров декодера точны. PWM admission не проводился: кандидат
отклонён по скорости. На иных MCU и физической плате не измерено.

В отдельной копии исходников базы применить patch с `git apply`, затем:

```sh
python tools/build_c_mac_test.py --avr-gcc avr-gcc
node tests/verify_c_mac.mjs
python tools/build.py --avr-gcc avr-gcc --backend c
node tests/verify_avr.mjs --backend c --verify-reset --oracle /path/to/oracle
```

Отчёты `Codecs/Speex/AVR/reports/c-byte-mac-*.json` содержат hashes, cycles
и решение. Native 16×16 C multiply остаётся в production. Число MUL само
по себе не предсказывает результат C-компилятора: важны переносы, расширения,
регистры и r1; ASM method B имеет другую последовательность инструкций.

## Разделение C IIR на фазы — отклонённые эксперименты

`nb3-c-iir-split.patch` и `nb3-c-iir-cached.patch`, база `098c3d9`, пути
относительно `Codecs/Speex/AVR/`. Первый выделяет десять обновлений коэффициентов
в отдельный цикл, затем выполняет тридцать шагов без age-test. Второй также
выносит два неизменных коэффициента в скаляры. Авторские C-прототипы сохраняют
modulo-32 math и точный порядок age updates, selectable C/architecture defines
и Xiph BSD notices. Проверены in-place и separate I/O.

На ATmega328P / AVR GCC 7.3 mixed Os/O2/O3+LTO оба точны на 9 100 кадрах
и проходят по 2 млн native direct/transposed LPC-сэмплов (Clang AMD64 O2,
fwrapv, fno-strict-aliasing), но **замедляют** полное декодирование на
2,7157% / 1,9606%. Flash у обоих +514 Б, static SRAM/stack прежние.
Кандидаты отклонены, production C IIR прежний. Ускорение ручного ASM тем же
алгоритмическим приёмом не доказывает результат C-компилятора. Точная причина
разницы здесь не установлена. Иные MCU и физическая плата не измерены;
PWM admission для отклонённых вариантов не проводился.

В отдельную копию базы применить один patch, собрать `--backend c` и выполнить
обычные `verify_pcm.py`/`verify_avr.mjs` из README кодека. Сохранённые отчёты:
`Codecs/Speex/AVR/reports/c-iir-phase-*.json`.

## Совместное чтение header 7/5/1: superseded noinline

`nb3-header-noinline.patch`, база `30f2a58`, пути относительно
`Codecs/Speex/AVR/`. Авторский C helper читает три bytes при offset 4..7,
возвращает тринадцать бит и обновляет курсор один раз. На прочих offsets,
нехватке данных или overflow делает generic reads по порядку 7/5/1. Xiph BSD
notices базы сохраняются; арифметика C, selectable ASM/C и Flash access прежние.

На ATmega328P / AVR GCC 7.3 mixed Os/O2/O3+LTO оба варианта точны на 9 100
кадрах каждого backend. Outlined уменьшает mean на 0,9807% ASM / 0,4980% C,
но выбранный inline — на 1,0891% / 0,5391%, быстрее по каждому stream mean
и меньше на 40/28 Б. В этой функции одна production source call site.
У noinline не было отдельного component-unit/PWM-гейта; полный текущий gate
и независимый header oracle относятся к выбранному inline. Иные MCU и
физическая плата не измерены. Отчёты `Codecs/Speex/AVR/reports/nb3-header-*`.

В новой игнорируемой копии воспроизвести базу (Python 3.12+ и tools из README):

```powershell
python -c "from pathlib import Path; import io, subprocess, tarfile; d=Path('Codecs/Speex/AVR/build/header-noinline-example'); d.mkdir(); data=subprocess.check_output(['git','archive','30f2a58:Codecs/Speex/AVR','src','tools','tests','vendor','handoff','reference','PORTING.md']); tarfile.open(fileobj=io.BytesIO(data)).extractall(d,filter='data')"
git apply --ignore-space-change --directory=Codecs/Speex/AVR/build/header-noinline-example docs/avr-asm-cookbook/examples/nb3-header-noinline.patch
python Codecs/Speex/AVR/build/header-noinline-example/tools/build.py --avr-gcc avr-gcc --backend asm
node Codecs/Speex/AVR/tests/verify_avr.mjs --backend asm --verify-reset --firmware Codecs/Speex/AVR/build/header-noinline-example/build/profile --oracle Codecs/Speex/AVR/build/reference --out Codecs/Speex/AVR/build/header-noinline-example/fixtures
```

Для C повторить последние две команды с `--backend c`. Patch проверен на
применение к базе; hashes исходных измеренных образов и full-speech результаты
сохранены в `nb3-header-variant-decision.json` и variant reports.

## Скалярный ASM-вход для одного сэмпла — исходный прототип

`nb3-scalar-boundary.patch`, база `db4f492`, добавляет отдельный ASM-вход для
трёх RAM-слов/трёх signed8 gains и одного Flash shape. Он сохраняет восемь
регистров вместо пятнадцати и использует прежнюю общую scaling/clamp/store
часть с packed-эпилогом. Код авторский, для ATmega328P hardware MUL / GNU AVR
ABI; исходные уведомления и Xiph BSD-лицензия сохранены. Действует прежнее
правило выбора архитектуры и явного разрешения ASM; при `--backend c` новый
вход не используется и двоичный образ совпадает с принятой C-версией.

AVR GCC 7.3 mixed Os/O2/O3+LTO: по 67 328 независимых пар ядра, ровно -37
тактов на вызов (227..242→190..205), полный набор guards/ABI/r1/clamp cases.
Ещё по 1 966 080 сэмплов short-controller ASM/C точны. Минимум контроллера
ASM +1 такт: ветка выбора тоже имеет цену. В целом ASM-декодере точны 14 278
кадров, среднее 31 потока -0,0179%, human speech -0,0182%; corpus max
125 613→125 500, coverage max 127 760→127 280. Flash 9 306→9 460 Б,
static SRAM 1 119 Б и peak stack 141 Б прежние. Сам исходный эксперимент не
включал ASM PWM/ISR. Теперь тот же машинный decoder/unit код включён в
основные исходники и прошёл обычный и +40% CPU PWM на всех 31 потоках;
доказательство переноса — `scalar-main-admission-audit.json`. Другие MCU
не измерены. Патч здесь сохраняет воспроизводимую исходную стадию.

В новой игнорируемой копии воспроизвести pinned базу и применить патч
(Python 3.12+, Git и toolchain из README кодека):

```powershell
python -c "from pathlib import Path; import io, subprocess, tarfile; d=Path('Codecs/Speex/AVR/build/scalar-boundary-example'); d.mkdir(); data=subprocess.check_output(['git','archive','db4f492:Codecs/Speex/AVR','src','tools','tests','vendor','handoff','reference']); tarfile.open(fileobj=io.BytesIO(data)).extractall(d,filter='data')"
git apply --ignore-space-change --directory=Codecs/Speex/AVR/build/scalar-boundary-example docs/avr-asm-cookbook/examples/nb3-scalar-boundary.patch
python Codecs/Speex/AVR/build/scalar-boundary-example/tools/build_long_pitch_test.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/build/scalar-boundary-example/tests/verify_long_pitch.mjs
node Codecs/Speex/AVR/build/scalar-boundary-example/tests/verify_long_pitch.mjs --scalar-only
python Codecs/Speex/AVR/build/scalar-boundary-example/tools/build_short_pitch_test.py --avr-gcc avr-gcc
node Codecs/Speex/AVR/build/scalar-boundary-example/tests/verify_short_pitch.mjs
python Codecs/Speex/AVR/build/scalar-boundary-example/tools/build.py --avr-gcc avr-gcc --backend asm
node Codecs/Speex/AVR/tests/verify_avr.mjs --backend asm --verify-reset --firmware Codecs/Speex/AVR/build/scalar-boundary-example/build/profile --oracle Codecs/Speex/AVR/build/reference --out Codecs/Speex/AVR/build/scalar-boundary-example/fixtures
```

Патч воспроизведён в отдельной копии: ASM decoder SHA-256
`31c10c12663c4e6a9e784693c4b72c19ba91c47feb86385f99a1db636081d4dc`
и оба unit-образа совпали с измеренными. C-образ также совпал с полностью
допущенной zero-vector C-версией. Полные замеры и проверка воспроизведения:
`Codecs/Speex/AVR/reports/scalar-boundary-experiment-*.json`.
