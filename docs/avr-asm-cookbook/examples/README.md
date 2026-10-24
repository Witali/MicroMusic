# Эксперимент: NB3 long-pitch fusion

`nb3-long-pitch-fusion.patch` — исходный C-прототип для ATmega328P / AVR GCC
7.3.0, база `30779f0`. Авторская переработка текущего restricted Xiph NB3;
исходные BSD-уведомления и лицензия `vendor/speex-1.2.1/COPYING` сохраняются.
Патч не включён в основной декодер. Только C backend; ASM/другие компиляторы
и полный PWM/ISR-gate для этого прототипа ещё не проверены. Native Clang
24.0.0git проверен на точность C; он игнорирует GCC `optimize("O2")`.

Из корня task worktree, после подготовки обычного reference/oracle и toolchain
из README кодека, создать **новую** игнорируемую копию и применить патч там:

```powershell
python -c "from pathlib import Path; import shutil; r=Path('Codecs/Speex/AVR'); d=r/'build/fused-pitch-example'; d.mkdir(); [shutil.copytree(r/n,d/n) for n in ['src','tools','tests','vendor','handoff','reference']]"
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
Перед production нужны независимые крайние значения истории/clamp, измерение
ASM/shared-vector формы с C fallback и весь corpus PWM с включёнными ISR.
