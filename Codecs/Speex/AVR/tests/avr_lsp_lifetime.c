/* Production math backends, independent non-LTO Xiph oracle and RAM guards. */
#include <stdint.h>
#include "nb3_interpolate.h"
#include "lsp.h"
void reference_lsp(const spx_lsp_t *,spx_coef_t *,int,char *);
void reference_interpolate(spx_lsp_t *,spx_lsp_t *,spx_lsp_t *,int,int,int,spx_word16_t);
int16_t lifetime_old[12],lifetime_next[12],lifetime_raw[12],lifetime_delta[12];
int16_t lifetime_out[12],lifetime_expected[12],lifetime_space[24];
volatile uint8_t lifetime_command,lifetime_status,lifetime_sub;
volatile int8_t lifetime_offset;
/* Original order-10 Xiph needs 624 B polynomial rows, 24 B pointer arrays,
 * 20 B cosine inputs and alignment on AVR. Keep 704 B plus two guards. */
uint8_t lifetime_arena[712];
static SPEEX_NB3_STAGE void lifetime_interpolate(int16_t *raw,const int16_t *delta,int16_t *out)
{
    speex_nb3_interpolate_validated(raw,delta,out);
}
int main(void)
{
    unsigned i;lifetime_status=1;
    for(;;){
        while(!lifetime_command){}
        if(lifetime_command==1){
            for(i=1;i<=10;i++){
                lifetime_raw[i]=lifetime_old[i];
                lifetime_delta[i]=(lifetime_next[i]>>2)-(lifetime_old[i]>>2);
            }
            lifetime_sub=0;
        }else if(lifetime_command==2){
            reference_interpolate(lifetime_old+1,lifetime_next+1,lifetime_expected+1,10,lifetime_sub,4,16);
            lifetime_interpolate(lifetime_raw+1,lifetime_delta+1,lifetime_out+1);lifetime_sub++;
        }else if(lifetime_command==3){
            reference_lsp(lifetime_old+1,lifetime_expected+1,10,(char *)lifetime_arena+4);
            lsp_to_lpc(lifetime_old+1,lifetime_out+1,10,0);
        }else{
            lsp_to_lpc(lifetime_space+5,lifetime_space+5+lifetime_offset,10,0);
        }
        lifetime_command=0;lifetime_status=2;
    }
}
