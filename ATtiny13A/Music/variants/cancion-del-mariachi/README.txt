07 · CANCIÓN DEL MARIACHI · ОТЧАЯННЫЙ

Фрагмент без вступления: исходные четверти 58..121, около 31,75 с
с паузой перед повтором. Музыкальный темп 126 BPM; восьмые и триоли
на точной сетке 1/6 четверти. Ведущая нейлоновая гитара FluidR3 GM24,
тихое пиано GM0 и безладовый бас GM35: уровни 15/7/10. Лёгкие ударные
с четвертным бас-барабаном/снейром и хай-хэтом между ними, уровень 4
(ослабление на два сдвига). Два резервных канала сохраняют затухание.
Полный исходник и описание новой аранжировки:
../../reference/cancion-del-mariachi/README.txt.

Flash 1014/1024 Б: код 744 Б, таблицы 270 Б. EEPROM 64 Б.
Три тональные партии, ударные и два резервных канала; очередь PWM 16 Б.
Синтез 18,75 кГц, PWM 37,5 кГц. Партитура во Flash; EEPROM читается.
Нейлоновая гитара взята из уже измеренного банка: яркая щипковая атака
и естественное замедление затухания. FluidR3-MIT.txt относится к тембрам.

Сборка из корня репозитория:
  python tools/arrange-mariachi.py
  python tools/build-rhythmic.py ATtiny13A/Music/variants/cancion-del-mariachi
  node tools/audit-release-engine.mjs cancion-del-mariachi

Прошить synth.hex во Flash, eeprom.hex в EEPROM. Фьюзы 7A/FF:
внутренний RC 9,6 МГц без CKDIV8. PWM PB1/OC0B, вывод 6; VCC 8, GND 4.
player.html — автономный плеер настоящего AVR-кода. preview.wav — первые
14 секунд той же прошивки с RC-приближением 9 кГц и highpass 35 Гц.
Отчёт исполнения: ../../../../web-player/reports/cancion-del-mariachi-release-verification.json.
