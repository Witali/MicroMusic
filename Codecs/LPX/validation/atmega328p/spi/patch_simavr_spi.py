"""Apply the isolated, source-pinned simavr1.6 master-clock timing correction.

No installed library is changed. The resulting object replaces only its existing
SPDR write handler in a separately linked observer; a trace hook records each scheduled
master-byte delay. Firmware and ROM observers never link this host module.
"""
import hashlib
from pathlib import Path

UPSTREAM_SHA256='88c5c301a0fd07e7a3e071ddc996882b430a9b8c1cf675cc616c298a10e0d77a'
COPYING_SHA256='8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903'
SOURCE_URL='https://raw.githubusercontent.com/buserror/simavr/v1.6/simavr/sim/avr_spi.c'
LICENSE_URL='https://raw.githubusercontent.com/buserror/simavr/v1.6/COPYING'


def patched(raw):
    if hashlib.sha256(raw).hexdigest()!=UPSTREAM_SHA256:
        raise ValueError('Expected exact upstream simavr1.6 SPI source')
    include=b'#include "avr_spi.h"'
    declaration=include+b'\nextern void lpx_simavr_spi_started(avr_t *, avr_spi_t *, uint8_t, uint16_t);'
    old=b'\t\tavr_cycle_timer_register_usec(avr, 100, avr_spi_raise, p); // should be speed dependent'
    new=b'''\t\t/* Master byte: eight SCK periods, using the actual SPR/SPI2X bits. */
\t\tstatic const uint8_t divisors[4] = {4, 16, 64, 128};
\t\tconst uint8_t setting = avr_regbit_get_array(avr, p->spr, 3);
\t\tconst uint16_t cycles = 8U * (divisors[setting & 3] >> ((setting >> 2) & 1));
\t\tlpx_simavr_spi_started(avr, p, v, cycles);
\t\tavr_cycle_timer_register(avr, cycles, avr_spi_raise, p);'''
    if raw.count(include)!=1 or raw.count(old)!=1:
        raise ValueError('Upstream SPI source does not match the minimal patch context')
    install=b'''
/* Explicit, version-pinned installation: the packaged library binds its own
 * avr_spi_init internally, so executable symbol interposition is insufficient.
 * Preserve the existing module, IRQs, input/read handlers and IO linked list.
 */
int lpx_simavr_spi_clock_install(avr_t *avr, avr_spi_t *p)
{
    const unsigned io = AVR_DATA_TO_IO(p->r_spdr);
    if (io >= MAX_IOs || p->io.avr != avr || !avr->io[io].w.c ||
            avr->io[io].w.param != p || avr->io[io].w.c == avr_spi_write)
        return 0;
    avr->io[io].w.c = avr_spi_write;
    return 1;
}
'''
    return raw.replace(include,declaration).replace(old,new)+install


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upstream',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if args.output.exists() or args.output.resolve()==args.upstream.resolve():
        parser.error('Use a fresh generated source path; upstream remains read only')
    args.output.write_bytes(patched(args.upstream.read_bytes()))
