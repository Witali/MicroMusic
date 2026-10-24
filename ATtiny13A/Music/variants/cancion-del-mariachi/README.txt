07 · CANCIÓN DEL MARIACHI · ОТЧАЯННЫЙ

Гитарный фрагмент: исходные четверти 0..121, около 58,1 с с паузой перед
повтором. Музыкальный темп 126 BPM; восьмые, триоли и мелкие украшения
на точной сетке 1/24 четверти. Ведущая нейлоновая гитара FluidR3 GM24,
тихая верхняя гитара и басовые струны: уровни 15/8/10. Два резервных
канала сохраняют затухание нот. Полный исходник и описание редукции:
../../reference/cancion-del-mariachi/README.txt.

Flash 954/1024 Б: код 554 Б, таблицы 400 Б. EEPROM 64 Б.
Три основных и два резервных тональных состояния, очередь PWM 16 Б.
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
