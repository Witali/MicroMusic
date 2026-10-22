# Независимая проверка MicroMusic PIC16F1503 в MPLAB X Simulator

**Статус на 21 октября 2026:** официальный MPLAB X IDE не был запущен в среде ChatGPT. Попытка скачать установщик MPLAB X IDE v6.35 для Linux с сервера Microchip не удалась: сервер вернул перенаправление на ошибку HTTP 401, прямое соединение контейнера с интернетом не разрешилось. **Файл `reference_our_emulator.json` — результат НАШЕГО JavaScript-эмулятора, а не MPLAB SIM.**

## Что подготовлено

- `micromusic_with_config.hex`: исходный PIC16F1503 Intel HEX с CONFIG1/CONFIG2, из проверенного проекта.
- `pic16-core.mjs`: версия нашего эмулятора, с которой сравниваем.
- `reference_our_emulator.json`: снимки состояния после выполнения 1, 2, 3, 4, 5, 8, 12, 24, 50, 100, 256, 1024 и 4096 машинных инструкций.
- `prepare_mdb.py`: создаёт командный файл для официального консольного симулятора MDB, входящего в MPLAB X IDE.
- `compare_logs.py`: вспомогательное сравнение отчётов MDB; парсер является экспериментальным и может потребовать адаптации к версии MDB.

## Проверка на установленном MPLAB X IDE

Официальная загрузка IDE для Linux/Windows: https://www.microchip.com/en-us/tools-resources/develop/mplab-x-ide

Для Windows в PowerShell:

```powershell
python prepare_mdb.py --mdb "C:\Program Files\Microchip\MPLABX\v6.35\mplab_ide\bin\mdb.bat"
python compare_logs.py
```

Для Linux (путь зависит от версии и настроек установки):

```bash
python3 prepare_mdb.py --mdb /opt/microchip/mplabx/v6.35/mplab_ide/bin/mdb.sh
python3 compare_logs.py
```

Если MDB установлен в другом каталоге, передайте фактический путь к `mdb.bat` или `mdb.sh`.

`mdb_official_output.log` будет содержать **реальные результаты MPLAB SIM**. До его получения нельзя утверждать, что модели PIC совпадают. Если `Print` не принимает один из SFR по имени, исключите его из списка `REGS` в `prepare_mdb.py` и сравните оставшиеся поля. Если `Stepi` не поддерживает большие блоки в вашей версии, разбейте количество инструкций на несколько команд.

## Что нужно сравнить

1. Сразу после Reset: начальные PC/WREG/STATUS/BSR и `OSCCON`.
2. После нескольких инструкций: изменение `OSCCON`, счётчик циклов и банковые регистры.
3. После настройки таймера: `TMR2`, `T2CON`, `PR2`, флаги `PIR1/PIE1/INTCON`.
4. После настройки PWM: `PWM3DCH`, `PWM3DCL`, `PWM3CON`; отдельно PWM3 pin-level модель, если этот периферийный блок поддерживается выбранной версией MPLAB SIM.
5. В реальном времени: период PWM 16 мкс при 16 МГц, прерывания каждые 80 мкс (62,5 и 12,5 кГц). Для фиксации времени использовать `Stopwatch`.

**Ограничение независимой проверки:** официальный MPLAB SIM сам является программной моделью и не заменяет измерения логическим анализатором на физическом PIC16F1503. Поддержка отдельных периферийных блоков зависит от версии IDE и DFP.

## Документация Microchip

- [MPLAB X IDE, установщик v6.35](https://www.microchip.com/en-us/tools-resources/develop/mplab-x-ide)
- [MDB User's Guide DS50002102](https://ww1.microchip.com/downloads/aemDocuments/documents/DEV/ProductDocuments/UserGuides/MDB-User-Guide.pdf), команды `Device`, `Hwtool SIM`, `Program`, `Reset`, `Stepi`, `Print`, `Stopwatch`.
- [Simulator documentation](https://developerhelp.microchip.com/xwiki/bin/view/software-tools/ides/x/debugging/simulator/)
- [PIC16F1503 datasheet DS40001607D](https://ww1.microchip.com/downloads/en/DeviceDoc/40001607D.pdf)
