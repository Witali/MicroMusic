# Оригинальный моноэтюд UM88

Исходные события созданы для проекта, CC0-1.0. Бинарный MIDI не использовался.
Звучат флейта, двухголосное пианино, бас и один процедурный генератор ударных.
Пример содержит паузу в начале, смену темпа, педаль, expression и pitch bend.
Использованы измеренные инструменты FluidR3; их MIT-уведомление включено в пакет.

```text
python tools/compile-universal-music.py ATtiny88/Music/universal/examples/mono-study/source-events.json --arrangement ATtiny88/Music/universal/examples/mono-study/arrangement.json --backend avr-asm --output build/mono-study --preview-seconds 6
```

Новый каталог `build/mono-study/` содержит полный результат. При необходимости
добавьте `--cpu-hz 12000000` и укажите другой выходной каталог.

- [Пакет 8 МГц](generated/player-package.json), [HEX](generated/synth.hex),
  [прослушивание](generated/preview.wav), [отчёт](generated/verification.json).
- [Пакет 12 МГц](profiles/12mhz/player-package.json),
  [прослушивание](profiles/12mhz/preview.wav), [отчёт](profiles/12mhz/verification.json).

Оба профиля: 3601 Б Flash, общий код 2772 Б, пять тональных голосов, без
сокращённых нот/хвостов, без неподдержанных событий, без клиппинга и underrun.
Минимум FIFO — 39 PWM-кадров; максимальный ISR — 51 такт. Различие длительностей
полных прогонов — около 0,618 мс. Это результаты цифровой модели.

Синтез 7,8125 кГц при 8 МГц и 11,71875 кГц при 12 МГц даёт различие верхних
гармоник при одинаковом темпе. Прослушивание позволяет сравнить их без
автоматической подгонки громкости. Объективная оценка субъективного качества
по одному RMS не заявляется.
