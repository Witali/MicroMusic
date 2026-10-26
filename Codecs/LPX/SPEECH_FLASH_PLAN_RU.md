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
- [ ] Измерить Flash по функциям и разделам ELF; отдельно учесть постоянную
  profiling/hardware обвязку и размер самого codec, не считать audio за код.
- [ ] Проверить ограниченную матрицу compiler/link/unroll/O2 settings при
  неизменном source snapshot. Не экономить на обязательных runner symbols
  или измерительной обвязке; сохранять точные flags и dependencies.
- [ ] Реализовать явно выбираемый compact-only build: только v5 speech,
  без удаления старых форматов из default build. Portable C fallback и
  аппаратное чтение Flash независимы от arithmetic selection.
- [ ] Проверить выбранные минимальные сборки: full PWM equality на8 потоках,
  native/model/C fallback, malformed/restart/partial tails, active IRQ,
  extra100 IRQ и64k-sample continuous controls. Недостаточно одного avr-size.
- [ ] Сохранить сравнительные размеры, timing/RAM/stack, границы поддержанных
  конфигураций, cookbook и focused commits после staged privacy inspection.

Приём: меньший Flash кода с прежними отсчётами и нулём новых underrun в
измеренных условиях ATmega328P16MHz/8kHz, queue512/prefill384. Не утверждать,
что самый маленький неподходящий по timing вариант поддержан. Отдельный
profile с меньшим набором форматов явно маркируется и не заменяет default.
