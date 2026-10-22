# Что ж ты не отвечаешь?

Прошивка TinyLPC для ATtiny13A, 9.6 МГц, PB1/OC0B PWM.

Flash: 997 байт включая 154 байт параметров речи.

Проверка:
```bash
python build_firmware.py
FRAMES=31 node verify.js
```

Эта прошивка не декодирует LPX3. Это компактный базовый декодер для сравнения с LPX3.
