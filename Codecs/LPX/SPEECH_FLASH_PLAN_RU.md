# Уменьшение Flash программы LPX

Прямое указание пользователя после компактного этапа: сосредоточиться на
размере программы во Flash. База `d2f79e15`; тот же branch/worktree.
Это отдельная задача размера, прежний19-round speed loop остаётся закрытым.

Baseline: общий v2/v3/v4/v5 binary около9172 байт без encoded stream,
1105 static SRAM. Качество всех выбранных записей заморожено: каждый
принятый вариант обязан сохранить полный PCM/PWM, не переоптимизировать audio.
Все новые outputs только в ignored build/lpx-speech-flash/.

- [x] Зафиксировать готовый quality/packing этап и immutable build snapshot
  source из `d2f79e15` отдельно от активных изменений.
- [x] Измерить Flash по функциям и разделам ELF; отдельно учесть постоянную
  profiling/hardware обвязку и размер самого codec, не считать audio за код.
- [x] Проверить ограниченную матрицу compiler/link/unroll/O2 settings при
  неизменном source snapshot. Не экономить на обязательных runner symbols
  или измерительной обвязке; сохранять точные flags и dependencies.
- [x] Реализовать явно выбираемый compact-only build: только v5 speech,
  без удаления старых форматов из default build. Portable C fallback и
  аппаратное чтение Flash независимы от arithmetic selection.
- [x] Проверить выбранные минимальные сборки: full PWM equality на8 потоках,
  native/model/C fallback, malformed/restart/partial tails, active IRQ,
  extra100 IRQ и64k-sample continuous controls. Недостаточно одного avr-size.
- [x] Сохранить сравнительные размеры, timing/RAM/stack, границы поддержанных
  конфигураций, cookbook и focused commits после staged privacy inspection.

Приём: меньший Flash кода с прежними отсчётами и нулём новых underrun в
измеренных условиях ATmega328P16MHz/8kHz, queue512/prefill384. Не утверждать,
что самый маленький неподходящий по timing вариант поддержан. Отдельный
profile с меньшим набором форматов явно маркируется и не заменяет default.

## Журнал

Атрибуция исходного9172B:7728B core,299B tables,778B playback/profiling,
367B runtime/vectors/data. Таблицы не основной резерв.
Проверены20 первоначальных и4 обоснованных сочетания лучших настроек
(24 configurations для каждого source profile). Лучший representative:
общий8030B, v5-only5910B. Рецепт:unroll1/tune0,Os,LTO,call-prologues,relax.
Source snapshot неизменен; текущий default preprocess совпал с ним по tokens.
Compact-only явно исключает legacy, class storage сокращён, max pulses3.

125 host tests:124 passed,1 optional hard-link skip. Common/only ASan/UBSan:
по613391 случая на464 inputs, в том числе8 enhanced speech prefixes;
sample_capped=0, reset exact. Шесть новых profile-specific tests прошли.
Выбранные сборки сохранили все8 frozen speech streams и прошли длинные
normal/+100IRQ/C controls; C точен, но не realtime. Общий optimized build
прошёл91 legacy stream с полным frozen PCM/PWM и нулём underrun.
Arithmetic unroll1 + selected global flags: C/ASM/forced-generic, каждый
по5768584 cases с активными IRQ, error/zero_error=0.

Сохранён [полный отчёт](research/speech-flash-2026-10-26/README.md) с13 JSON
evidence files и cookbook. На8 прежних enhanced streams: common7889–8030B,
only5909–5910B против9171–9172B; static SRAM1105/1085B. Средние wall cycles
958.490→846.641/785.019. Полный PWM совпадает; main и normal/+100IRQ ASM
underruns=0. Common91 legacy streams:2912000 samples,2188276589 cycles,
underruns=0. C fallback точен по полезным значениям, но8kHz не выдерживает.
Физическая плата не измерена; вывод ограничен16MHz/8kHz queue512/prefill384,
LPC segments2. Default build не менялся; small-code flags и only profile
выбираются явно. Исходники/feature implementation и evidence сохранены
отдельными focused commits после staged privacy inspection.
