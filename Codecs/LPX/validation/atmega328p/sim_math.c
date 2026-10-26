// Independent complete-firmware arithmetic runner, using the public simavr API.
// Same tool/dependency provenance as sim_profile.c; no simavr source copied.
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "sim_avr.h"
#include "sim_elf.h"
static uint32_t symbol(elf_firmware_t* fw,const char* name){
    for(uint32_t i=0;i<fw->symbolcount;i++)
        if(!strcmp(fw->symbol[i]->symbol,name))return fw->symbol[i]->addr&0xffff;
    fprintf(stderr,"Missing symbol %s\n",name);exit(2);
}
static uint32_t read32(avr_t* cpu,uint32_t a){
    uint32_t v=0;for(unsigned i=0;i<4;i++)v|=(uint32_t)cpu->data[a+i]<<(8*i);return v;
}
int main(int argc,char** argv){
    if(argc!=2)return 2;
    elf_firmware_t fw={0};if(elf_read_firmware(argv[1],&fw)<0)return 3;
    fw.frequency=16000000;
    avr_t* cpu=avr_make_mcu_by_name("atmega328p");if(!cpu||avr_init(cpu)<0)return 4;
    avr_load_firmware(cpu,&fw);cpu->frequency=16000000;
    const uint32_t done=symbol(&fw,"math_done"),error=symbol(&fw,"math_error");
    const uint32_t zero=symbol(&fw,"math_zero_error"),cases=symbol(&fw,"math_cases");
    const uint32_t irq=symbol(&fw,"math_irqs"),backend=symbol(&fw,"math_backend");
    int state=cpu_Running;
    while(cpu->cycle<UINT64_C(3000000000)&&!cpu->data[done]&&state!=cpu_Crashed&&state!=cpu_Done)
        state=avr_run(cpu);
    printf("{\"done\":%u,\"error\":%u,\"zero_error\":%u,\"cases\":%u,\"irqs\":%u,\"backend\":%u,\"cycles\":%llu}\n",
        cpu->data[done],cpu->data[error],cpu->data[zero],read32(cpu,cases),read32(cpu,irq),
        cpu->data[backend],(unsigned long long)cpu->cycle);
    return !cpu->data[done]||cpu->data[error]||cpu->data[zero]||!read32(cpu,irq);
}
