# Архив стереопрофиля UM88 v1

Точная копия общего кода из c4dec96 для сохранённого `songs/lumiere-stereo`.
Текущий общий драйвер заново собирает моно и стерео; этот профиль хранит
исторический код. Архивный ROM, партитура и прежний полный аудит находятся в
`songs/lumiere-stereo/`; контрольные суммы закреплены в `provenance.json`.

AVR GCC 7.3.0, `-mmcu=attiny88 -Os -fno-jump-tables -ffunction-sections
-fdata-sections -Wl,--gc-sections -DUM_ENABLE_AVR_ASM=1 -DUM_SONG_ADDRESS=2784`.
Vendor include остаётся в `../../vendor/ATtiny_DFP/3.4.278/include`, без копирования
или редактирования определений Microchip. Музыкальный блок исходного ROM начинается
с адреса 2784; формат и JSON находятся в `songs/lumiere-stereo/`.
