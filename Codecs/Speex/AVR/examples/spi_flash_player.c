/* ATmega328P, 16 MHz. Compressed packets come from the shared SPI reader.
 * The decoder arithmetic backend is selected independently at build time. */
#include "spi_sample.h"
#include "AvrSpiFlashReader.h"

/* Reuse the production output conversion, queue and timer ISR unchanged.
 * The embedded-data main is unreferenced and removed by section GC/LTO. */
#define main speex_embedded_player_unused_main
#if SPEEX_SPI_WIDEBAND
#include "../src/wb_player.c"
#else
#include "../src/player.c"
#endif
#undef main

volatile uint32_t speex_spi_frames;
#if SPEEX_SPI_CAPTURE_PCM
const int16_t *volatile speex_spi_pcm;
volatile uint8_t speex_spi_chunks, speex_spi_samples;
#if SPEEX_SPI_WIDEBAND
static void spi_output(const int16_t *samples, uint8_t count, void *context)
{
    speex_spi_pcm = samples;
    speex_spi_samples = count;
    ++speex_spi_chunks;
    output(samples, count, context);
}
#endif
#endif

int main(void)
{
    AvrSpiFlashReader reader;
    uint32_t frames = SPEEX_SPI_FRAME_COUNT;
    uint8_t i;
    cli();
    speex_audio_init();
#if SPEEX_SPI_WIDEBAND
    speex_wb1_init();
#else
    speex_avr_init();
#endif
    avr_spi_flash_init(&reader);
    if (!avr_spi_flash_begin(&reader, SPEEX_SPI_ADDRESS, SPEEX_SPI_BYTES)) {
        speex_player_error = 1;
    } else {
        while (frames--) {
            for (i = 0; i < SPEEX_SAMPLE_PACKET_BYTES; ++i) {
                int16_t value = avr_spi_flash_read(&reader);
                if (value < 0) {
                    speex_player_error = 2;
                    break;
                }
                packet[i] = (uint8_t)value;
            }
            if (speex_player_error) break;
#if SPEEX_SPI_WIDEBAND
#if SPEEX_SPI_CAPTURE_PCM
            if (speex_wb1_decode(packet, sizeof(packet), spi_output, 0)) {
#else
            if (speex_wb1_decode(packet, sizeof(packet), output, 0)) {
#endif
#else
            if (speex_avr_decode(packet, sizeof(packet), pcm)) {
#endif
                speex_player_error = 3;
                break;
            }
#if SPEEX_SPI_CAPTURE_PCM && !SPEEX_SPI_WIDEBAND
            speex_spi_pcm = pcm;
            speex_spi_samples = 160;
            ++speex_spi_chunks;
#endif
            ++speex_spi_frames;
        }
    }
    avr_spi_flash_close(&reader);
    input_finished = 1;
    if (!speex_player_started) speex_player_done = 1;
    while (!speex_player_done) { }
    for (;;) { }
}
