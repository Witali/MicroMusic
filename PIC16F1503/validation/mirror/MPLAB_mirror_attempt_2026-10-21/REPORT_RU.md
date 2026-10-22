# PIC16F1503 MicroMusic — попытка независимой проверки через MPLAB X

Дата: 21 октября 2026 года. Проверяемый файл: `micromusic_with_config.hex`.

## Установщик и источники

1. Альтернативное зеркало, использованное в опубликованном Dockerfile `dataspeedinc/mplabx` (https://hub.docker.com/r/dataspeedinc/mplabx/dockerfile):
   `https://dataspeedincorp-my.sharepoint.com/:u:/g/personal/khallenbeck_dataspeedinc_com/IQARMrlMtl4LToVZu9-EXZ12AdKSrpqxqN17H8pCn1z7SUU?download=1`
2. Официальный CDN:
   `https://ww1.microchip.com/downloads/aemDocuments/documents/DEV/ProductDocuments/SoftwareTools/MPLABX-v6.35-linux-installer.tar`
3. Ожидаемый SHA-256, указанный на официальной странице v6.35 и в Dockerfile:
   `4c747363dcfb315726439f968d0e25b0b17214bb9ba5d2fd4a7f3bab28c56705`

## Фактические результаты попытки загрузки

- Linux x86_64, свободно около 30 ГБ.
- `curl -I -L` для альтернативного SharePoint: `curl: (6) Could not resolve host: dataspeedincorp-my.sharepoint.com`.
- Проверка через DNS `socket.getaddrinfo`: имена github.com, ww1.microchip.com и dataspeedincorp-my.sharepoint.com не разрешаются (`gaierror`). Переменная `NETWORK=caas_packages_only`, прямой внешний доступ контейнера отключён.
- Служба скачивания файлов не смогла получить ZIP/TAR с альтернативного SharePoint (ограничение доступа URL), а запросы к официальному CDN v6.35/v6.30 также завершились ошибкой загрузки.
- MPLAB X **не скачан, не установлен и не запущен**. Журнал MDB/официального SIM **не существует**. Никаких независимых измерений по MPLAB SIM не сделано.

## Повторные внутренние тесты (НЕ независимые)

- Пройдены 107/107 модульных тестов нашего PIC-эмулятора, `pic_internal_unit_tests.log`.
- Проверка структуры прошивки через Python `tests/test_firmware.py`: PASS; занято 1157 значимых слов программы; 216 байт событий, 15 секций, 18 форм волн.
- Выполнена свежая 14-секундная эмуляция того же PIC HEX нашим JS-ядром: 174997 прерываний, 0 опустошений очереди, максимальная глубина стека 4. Эти значения приведены в `local_14s_results.json`.
- SHA-256 HEX `7787e6dae4f115a36cf4f4a9054ed02c74411106efb02ba861195755854ae578`.

## Как выполнить настоящий независимый тест

1. На Linux с интернетом запустить `bash download_verify_mplab.sh .`. Скрипт пробует зеркало и Microchip, проверяет контрольную сумму и только после этого распаковывает архив; не выполняет неподтверждённый установщик автоматически.
2. Установить MPLAB X IDE с модулем поддержки 8-bit PIC и симулятором. Проверить существование `mdb.sh` (обычно `/opt/microchip/mplabx/v6.35/mplab_ide/bin/mdb.sh`).
3. Перейти в `comparison_kit/` и вызвать `python3 prepare_mdb.py --mdb /opt/microchip/mplabx/v6.35/mplab_ide/bin/mdb.sh`.
4. Сохранить `mdb_official_output.log` и выполнить `python3 compare_logs.py`. Если команды отличаются в установленной версии, свериться с официальным MDB User's Guide и адаптировать скрипт. Командный сценарий не был проверен на реальном MDB.
5. При расхождении прислать журнал для поинструкционной проверки.

Важно: файл `comparison_kit/reference_our_emulator.json` **не** получен из официального Microchip Simulator, а является результатом нашего JS-интерпретатора.
