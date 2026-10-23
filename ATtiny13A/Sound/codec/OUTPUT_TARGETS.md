# Вывод обученной речи

`tools/export-speech.py` отделяет обученную модель от способа вывода. Коэффициенты
подбирает кодировщик; профиль задаёт арифметику, частоту и ограничения устройства.
Экспорт не меняет громкость и не добавляет скрытую обработку постоянной составляющей.

| Профиль | Вход | Выход |
| --- | --- | --- |
| `--target pc --arithmetic float` | `period-colored-v1` | упакованная модель, float32 PCM и WAV |
| `--target pc --arithmetic fixed` | `period-colored-v1` или `period-fixed-v1` | целочисленная модель, точный unsigned 8-bit PCM и WAV |
| `--target avr --mcu attiny13` | те же модели | целочисленные данные, C-заголовок; сборка через AVR-адаптер |
| `--target mcu --mcu <имя>` | те же модели | переносимые целочисленные данные и C-заголовок |

Все текущие варианты работают с 7500 Гц. Конвертация float → fixed меняет
арифметику и должна сопровождаться повторным автоматическим подбором параметров
через точный целочисленный декодер. Экспорт готовой модели `period-fixed-v1`
сохраняет её отсчёты. Обратная конвертация fixed → float не определена.

```powershell
python tools/export-speech.py --model ATtiny13A/Sound/research/period-balanced/chego/model.json --output build/export-pc --target pc
python tools/export-speech.py --model build/fixed/chego/model.json --output build/export-fixed --target pc --arithmetic fixed
python tools/export-speech.py --model build/fixed/chego/model.json --output build/export-avr --target avr --mcu attiny13 --build --avr-bin C:/Work/MicroMusic/build/toolchains/avr-7.3.0/bin --node C:/Work/MicroMusic/build/toolchains/node-22.22.3/node.exe
python tools/export-speech.py --model build/fixed/chego/model.json --output build/export-mcu --target mcu --mcu cortex-m0 --profile build/cortex-m0.json
```

Профиль другого контроллера — JSON:

```json
{
  "schema": "speech-output-profile-v1",
  "name": "cortex-m0-fixed",
  "sample_rate": 7500,
  "flash_bytes": 16384,
  "sram_bytes": 2048,
  "cpu_hz": 48000000
}
```

Поле `adapter`, если задано, содержит путь Python-скрипта относительно корня
репозитория или абсолютный путь. При явном `--build` вызывается
`python <adapter> --model <model.json> --output <firmware-directory>`.
Адаптер может создать `build.json` с измерениями. Наличие данных в C-массиве
не означает наличия декодера для выбранного контроллера. AVR-заголовок использует
`PROGMEM`; доступ к нему требует `pgm_read_byte`.

В `manifest.json` записаны профиль, хеши артефактов, точность roundtrip PCM,
размер данных и статус сборки. `flash_data_fits` учитывает только данные.
Из отчёта AVR-адаптера переносятся измеренный полный Flash, размер данных
и явный статус `oversized`, если код с данными не помещается. Статус `verified`
допускается только с соответствующими хешами модели/образа и успешным отчётом
эмуляторов. Тогда сохраняются интервалы отсчётов и минимальный указатель стека.
Расход SRAM и длительность самих вычислений не выводятся из интервала отсчётов.
Ограничения профиля не выдают измерения и не разрешают автоматически менять модель.
Если адаптер отсутствует, обычный экспорт остаётся доступен, а `--build`
завершается ошибкой. Ошибки сборки сохраняются в `build.log`.

Для обучения используется API:

```python
from speech_targets import resolve_profile, decode_for_profile
profile = resolve_profile('avr', mcu='attiny13')
pcm = decode_for_profile(candidate_model, profile)
score = objective.spectrum(pcm)
```

`pcm` включает округление и насыщение выбранного декодера. STOI и спектральную
ошибку нужно считать по этим же отсчётам при автоматическом поиске коэффициентов.
Для fixed нормировка равна `(DAC_uint8 - 128) / 128`, без удаления смещения.
