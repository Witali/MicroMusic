/* Independent original Xiph oracle; production fused/separate and direct ABI. */
#include <stdint.h>
#include "nb3_interpolate.h"
#include "lsp.h"
void reference_lsp(const spx_lsp_t *,spx_coef_t *,int,char *);
void reference_interpolate(spx_lsp_t *,spx_lsp_t *,spx_lsp_t *,int,int,int,spx_word16_t);
int16_t margin_old[12],margin_next[12],margin_delta[12],margin_raw_fused[12],margin_raw_separate[12];
int16_t margin_lsp_actual[12],margin_lsp_expected[12],margin_coef_fused[12],margin_coef_separate[12],margin_coef_expected[12];
uint8_t margin_arena[712],margin_work[576];
volatile uint16_t margin_addresses[3];
volatile uint8_t margin_command,margin_status,margin_sub;
static SPEEX_NB3_STAGE void margin_codebook(int16_t *r,const int16_t *d,int16_t *o)
{speex_nb3_interpolate_codebook(r,d,o);}
static SPEEX_NB3_STAGE void margin_advance(int16_t *r,const int16_t *d,int16_t *o)
{speex_nb3_advance_codebook(r,d,o);}
static SPEEX_NB3_STAGE void margin_advance_c(int16_t *r,const int16_t *d,int16_t *o)
{speex_nb3_advance_codebook_c(r,d,o);}
int main(void)
{
    unsigned i;margin_addresses[0]=(uint16_t)(uintptr_t)margin_work;margin_status=1;
    for(;;){
        while(!margin_command){}
        if(margin_command==1){
            for(i=1;i<=10;i++){
                margin_raw_fused[i]=margin_raw_separate[i]=margin_old[i];
                margin_delta[i]=(margin_next[i]>>2)-(margin_old[i]>>2);
            }
            margin_sub=0;
        }else if(margin_command==2){
            reference_interpolate(margin_old+1,margin_next+1,margin_lsp_expected+1,10,margin_sub,4,16);
            reference_lsp(margin_lsp_expected+1,margin_coef_expected+1,10,(char *)margin_arena+4);
            margin_codebook(margin_raw_separate+1,margin_delta+1,margin_lsp_actual+1);
            for(i=1;i<=10;i++)margin_coef_separate[i]=margin_lsp_actual[i];
            lsp_to_lpc(margin_coef_separate+1,margin_coef_separate+1,10,0);
            speex_nb3_interpolate_lpc(margin_raw_fused+1,margin_delta+1,margin_coef_fused+1);
            margin_sub++;
        }else if(margin_command==3 || margin_command==4){
            int16_t *r=(int16_t *)(uintptr_t)margin_addresses[0];
            const int16_t *d=(const int16_t *)(uintptr_t)margin_addresses[1];
            int16_t *o=(int16_t *)(uintptr_t)margin_addresses[2];
            if(margin_command==3)margin_advance(r,d,o);else margin_advance_c(r,d,o);
        }else{
            reference_interpolate(margin_old+1,margin_next+1,margin_lsp_expected+1,10,margin_sub,4,16);
        }
        margin_command=0;margin_status=2;
    }
}
