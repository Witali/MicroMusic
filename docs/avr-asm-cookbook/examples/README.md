# Эксперименты NB3

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

## Скалярный ASM-вход для одного сэмпла — ожидает PWM/ISR-допуска

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
static SRAM 1 119 Б и peak stack 141 Б прежние. **ASM PWM/ISR не проверялся**;
патч пока не включён в основные исходники. Другие MCU не измерены.

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
