/* Host-only GPIO/SPI bridge contract with compiled vendor metadata. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sim_io.h"
#include "spi_flash_bridge.h"

static avr_t *cpu;
static LpxSpiBridge bridge;
static avr_irq_t *cs;

static uint8_t transfer(uint8_t value){
    avr_spi_t *p=bridge.spi;unsigned io=AVR_DATA_TO_IO(p->r_spdr);
    cpu->io[io].w.c(cpu,p->r_spdr,value,cpu->io[io].w.param);
    while(!avr_regbit_get(cpu,p->spi.raised))assert(avr_run(cpu)==cpu_Running);
    return cpu->io[io].r.c(cpu,p->r_spdr,cpu->io[io].r.param);
}

static void select_pin(bool high){
    uint8_t bit=(uint8_t)(1u<<bridge.hw.cs_bit);
    if(high)cpu->data[bridge.hw.port]|=bit;else cpu->data[bridge.hw.port]&=(uint8_t)~bit;
    avr_raise_irq(cs,high?1:0);
}

static void open_at(uint32_t address){
    select_pin(false);
    assert(transfer(0x0b)==0);
    assert(transfer((uint8_t)(address>>16))==0);
    assert(transfer((uint8_t)(address>>8))==0);
    assert(transfer((uint8_t)address)==0);
    assert(transfer(0xff)==0);
}

int main(int argc,char **argv){
    assert(argc==2);FILE *file=fopen(argv[1],"rb");assert(file);
    uint8_t bytes[74];assert(fread(bytes,1,sizeof(bytes),file)==sizeof(bytes) && fgetc(file)==EOF);fclose(file);
    uint32_t m[37];for(unsigned i=0;i<37;i++)m[i]=bytes[2*i]|((uint32_t)bytes[2*i+1]<<8);
    LpxSpiHardware h={m[20],m[21],m[22],m[23],m[24],m[25],m[26],m[27],m[28],
        m[29],m[30],m[31],m[32],m[33],m[34],m[35],m[36]};
    uint8_t *image=malloc(LPX_W25Q128_IMAGE_BYTES);assert(image);
    memset(image,0xff,LPX_W25Q128_IMAGE_BYTES);image[0x010203]=0x5a;image[0x010204]=0xa6;image[0x010206]=0x71;
    cpu=avr_make_mcu_by_name("atmega328p");assert(cpu && avr_init(cpu)==0);cpu->frequency=16000000;
    memset(cpu->flash,0,(size_t)cpu->flashend+1);
    assert(lpx_spi_bridge_attach(&bridge,cpu,image,LPX_W25Q128_IMAGE_BYTES,&h,NULL));
    avr_ioport_t *gpio=NULL;
    for(avr_io_t *io=cpu->io_port;io;io=io->next)if(io->kind && !strcmp(io->kind,"port")){
        avr_ioport_t *candidate=(avr_ioport_t *)io;if(candidate->r_port==h.port)gpio=candidate;
    }
    assert(gpio);cs=avr_io_getirq(cpu,AVR_IOCTL_IOPORT_GETIRQ(gpio->name),(int)h.cs_bit);assert(cs);
    cpu->data[h.ddr]=(uint8_t)((1u<<h.cs_bit)|(1u<<h.mosi_bit)|(1u<<h.sck_bit));
    avr_regbit_set(cpu,bridge.spi->spe);avr_regbit_set(cpu,bridge.spi->mstr);
    for(unsigned bit=0;bit<3;bit++)avr_regbit_setto(cpu,bridge.spi->spr[bit],bit==2);
    open_at(0x010203);assert(transfer(0xff)==0x5a);assert(transfer(0xff)==0xa6);select_pin(true);
    /* Explicit seek skips stored bytes without forcing a remaining tail read. */
    open_at(0x010206);assert(transfer(0xff)==0x71);select_pin(true);
    assert(lpx_spi_bridge_valid(&bridge));
    LpxW25q128Stats stats=lpx_w25q128_get_stats(&bridge.flash);
    assert(stats.command_bytes==2 && stats.address_bytes==6 && stats.dummy_bytes==2 && stats.read_bytes==3
           && stats.cs_assertions==2 && stats.cs_deassertions==2 && stats.unsupported_commands==0);
    printf("{\"status\":\"PASS\",\"completed_bytes\":13,\"vendor_metadata_fields\":37,\"explicit_seeks\":2,\"player_images\":0}\n");
    avr_terminate(cpu);free(image);return 0;
}
