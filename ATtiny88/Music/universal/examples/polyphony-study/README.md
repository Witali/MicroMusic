# Восемь одновременных голосов UM88

Оригинальные события созданы для проекта, CC0-1.0; MIDI-бинарник не создавался.
Восемь партий используют флейту, бас и виолончель из измеренного банка FluidR3.
Дополнительно работает процедурный генератор ударных. Есть смены темпа и
программы, педаль, CC7 volume, CC11 expression, pitch bend, отпускание нот
и All Notes Off. Все 16 нотных атак сохранены; сокращённых хвостов,
пропущенных/слишком коротких нот, заменённых ударных и неподдержанных событий нет.

```text
python tools/compile-universal-music.py ATtiny88/Music/universal/examples/polyphony-study/source-events.json --arrangement ATtiny88/Music/universal/examples/polyphony-study/arrangement.json --backend avr-asm --buffer-frames 192 --output build/eight-voices --preview-seconds 5
```

- Кольцо 192: [пакет](generated/player-package.json), [HEX](generated/synth.hex),
  [прослушивание](generated/preview.wav), [проверка](generated/verification.json).
- Кольцо 128: [пакет](profiles/buffer-128/player-package.json),
  [HEX](profiles/buffer-128/synth.hex), [проверка](profiles/buffer-128/verification.json).

Оба профиля: ATtiny88 8 МГц, восемь независимых тональных голосов, моно,
Flash 3835/8192 Б, 259 управляющих тиков. Синтез 7,8125 кГц, PWM 31,25 кГц.
Полный цикл и повтор прошли с активными IRQ: без underrun, потерь IRQ и
клиппинга. Микшер — максимум 339 тактов, ISR — 47, управление — 18410.
Минимум FIFO 98 кадров при кольце 192 и 34 при кольце 128. Минимум SP733;
запас над кольцом соответственно 29/93 Б. Проверено цифровой моделью.

Это пример измеренной нагрузки, не гарантия любых восьмиголосных MIDI.
Грамматика, тембровый банк, точность времени и ограничения контроллеров
описаны в [формате](../../FORMAT_RU.md) и [аранжировке](../../ARRANGEMENT_RU.md).
