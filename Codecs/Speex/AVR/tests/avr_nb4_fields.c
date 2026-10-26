#include <stdint.h>
#include "nb4_subframe.h"
uint8_t nb4_field_buffer[384],nb4_field_indices[8];
volatile uint16_t nb4_field_address,nb4_field_header;
volatile uint8_t nb4_field_sub,nb4_field_command,nb4_field_status;
int main(void)
{
    nb4_field_address=(uint16_t)(uintptr_t)nb4_field_buffer;nb4_field_status=1;
    for(;;){
        while(!nb4_field_command){}
        nb4_field_header=speex_nb4_unpack_subframe((const uint8_t *)(uintptr_t)nb4_field_address,nb4_field_sub,nb4_field_indices);
        nb4_field_command=0;nb4_field_status=2;
    }
}
