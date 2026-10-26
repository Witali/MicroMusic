# Уточнение выбранных профилей8/12/16

`refine_bitrate_profile.py` уточняет существующий legacy v2/v3 поток по
полному mono PCM16/8kHz WAV. Это явный дополнительный PC search; defaults
старого WAV encoder не заменены. Decoder, format, таблицы и C fallback
не меняются. Все изменения оцениваются через native decoder и integer model.

```text
python tools/refine_bitrate_profile.py reference.wav baseline8.l4hy out8 --audio-kbps 8 --seed high12.l4hy --seed high16.l4hy
```

`--seed` необязателен и может повторяться. Seed обязан описывать ту же
полную запись; v4/v5 speech seed точно преобразуется в старый формат на
ПК, включая дополнительные импульсы. MCU не требуется поддержка v5.
Поиск остаётся ограниченным: beam8, family-specific lambda grid, до двух
уточнений границы на seed. Он не доказывает глобального оптимума.

Предел по умолчанию:20-byte header плюс audio budget8/12/16 кбит/с за
полную длительность. `--max-bytes` задаёт явный предел **всего файла**.
Исходный baseline обязан в него помещаться. Длины1..64000 samples
поддерживаются без удаления начала/конца; изменения gain и задержки нет.
Для музыки/синтетики используйте `--kind music`, без речевой STOI.

Прежний поток остаётся допустимым откатом. Выбранный вариант не увеличивает
полную PCM16 SSE и не снижает речевую STOI; такие же floors проверяются
после фактического общего PWM transfer. Пиковая ошибка измеряется отдельно
и всё ещё может вырасти. Меньшая MSE не обещает лучшего субъективного звука.

Выход:audio.l4hy,decoded.wav,report.json. JSON содержит фактический полный
и payload bitrate, PCM/PWM hashes, before/after metrics и число оценок.
Новый поток ещё требует отдельного AVR timing admission: формат прежний,
но конкретное содержимое может менять стоимость чтения Rice/pitch.
В report.json это обозначено `avr_cycles_measured=false`.
См. [стенд AVR](../../validation/atmega328p/README.md) и
[измеренный протокол профилей](../../PROFILE_DEVELOPMENT_PLAN_RU.md).

Основной PC speedup отдельно измерен без изменения потока:
[отчёт](../../research/encoder-profiles-2026-10-26/README.md).
Cold JIT и warm search — разные величины. Для нового входа больше seeds
и beam8 могут увеличить число проверок, несмотря на ускорение одной оценки.
