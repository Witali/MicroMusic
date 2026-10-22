# Речь на ATtiny13A

- `codec/` — последняя ветка MiniLPC HQ4 balanced/max-STOI: кодировщик, модель, замороженные параметры и AVR-ассемблер.
- `fast-encoder/` — C-ускоритель обучения на компьютере; это не C-прошивка микроконтроллера.
- `research/stages/` — результаты TinyLPC, LPC2-Lite, AutoLPC2, Keyframe/Adaptive, MiniLPC и HQ2/HQ3/HQ4 с контрольными суммами исходников соответствующих коммитов.

Последние balanced-образы: 959/885/1024 Б; декодер 406 Б, 7,5 кГц PCM, PWM на PB1. Максимальный STOI-вариант первой фразы занимает 957 Б. Значения STOI взяты из сохранённых отчётов; новый импорт проверил сборку и отсчёты, а не повторное обучение.

Проверка всех четырёх замороженных образов без исходных WAV и ZIP, из корня репозитория:

```text
python tools/verify-frozen-speech.py --avr-bin build/toolchains/avr-7.3.0/bin --report build/frozen-speech-verification.json
```

Нужен Node.js в PATH. Сценарий собирает ассемблер в `build/`, проверяет хеши прошивки и всех PCM по исторической карте исходников. `trained/chego/backup_09018.npz` сохранён как отдельный снимок поиска максимального STOI; это исследовательский источник альтернативного результата.

Изолированная сборка сохранённого ассемблера выполняется из каталога фразы с файлом `speech.hq`:

```text
avr-gcc -mmcu=attiny13 -nostdlib -Wl,-Ttext=0 -x assembler firmware.S -o firmware.elf
avr-objcopy -O binary firmware.elf firmware.bin
```

Для полного обучения установите зависимости из `codec/requirements.txt` и восстановите внешние канонические WAV из исходного архива в каталог эталонов. `build_hq4.py` использует Clang AVR и llvm-objcopy; `make_player_hq4.py` создаёт удалённые при очистке HTML. Прежние README описывают полный исходный архив, включая исключённые из репозитория аудио и сборочные результаты.

[Общий указатель истории и проверок](../../SOURCE_IMPORTS_RU.md).
