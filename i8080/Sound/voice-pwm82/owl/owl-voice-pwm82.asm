; Intel 8080: lossless PCM4 word RLE, two uniform 82T pulses/sample. INT/WAIT/HOLD inactive.
; BC=PCM word; E=word count; D=literal/RLE phase page; SP=ROM cursor. No RAM, CALL or PUSH.
; High nibble first, codes 4/15 swapped. Five 129B dispatch pages: 8B cells, last cell 9B.
; DCR E in phase 2; Z MUST survive until phase 3/4 JNZ. ORI 0 padding only when Z is dead.
; C fallback: ../voice32/voice.c; ASM requires explicit architecture + enable flag.
; Final full PWM period precedes a silent 7T HLT tail.
    ORG 00000H
    JMP VOICE

    ORG 01100H
VOICE:
    DI
    LXI SP,STREAM
    POP D
    DCR E
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    PCHL

    ORG 00003H
HALT:
    HLT

    ORG 00004H
END_STREAM:
    DB 001H,000H

    ORG 03800H
P0_L0:
    EI
    DI
    JMP P0_L0_BODY

    ORG 00006H
P0_L0_BODY:
    MOV A,C
    RLC
    RLC
    RLC
    ANI 078H
    MOV L,A
    MVI H,039H
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    DI
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03808H
P0_L1:
    EI
    NOP
    DI
    JMP P0_L1_BODY

    ORG 00026H
P0_L1_BODY:
    MOV A,C
    RLC
    RLC
    RLC
    ANI 078H
    MOV L,A
    MVI H,039H
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03810H
P0_L2:
    EI
    NOP
    NOP
    DI
    JMP P0_L2_BODY

    ORG 00045H
P0_L2_BODY:
    MOV A,C
    RLC
    RLC
    RLC
    ANI 078H
    MOV L,A
    MVI H,039H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    NOP
    DI
    NOP
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03818H
P0_L3:
    EI
    NOP
    NOP
    NOP
    DI
    JMP P0_L3_BODY

    ORG 00064H
P0_L3_BODY:
    MOV A,C
    RLC
    RLC
    RLC
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    ANI 078H
    MOV L,A
    DI
    MVI H,039H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03878H
P0_L4:
    EI
    NOP
    NOP
    NOP
    NOP
    DI
    JMP P0_L4_BODY

    ORG 00081H
P0_L4_BODY:
    MOV A,C
    RLC
    RLC
    RLC
    ANI 078H
    MOV L,A
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    MVI H,039H
    NOP
    MOV A,A
    DI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03828H
P0_L5:
    EI
    JMP P0_L5_BODY

    ORG 0009EH
P0_L5_BODY:
    MOV A,C
    MOV A,A
    DI
    RLC
    RLC
    RLC
    ANI 078H
    MOV L,A
    MVI H,039H
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03830H
P0_L6:
    EI
    JMP P0_L6_BODY

    ORG 000BFH
P0_L6_BODY:
    MOV A,C
    RLC
    MOV A,A
    DI
    RLC
    RLC
    ANI 078H
    MOV L,A
    MVI H,039H
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03838H
P0_L7:
    EI
    JMP P0_L7_BODY

    ORG 000E0H
P0_L7_BODY:
    MOV A,C
    RLC
    RLC
    MOV A,A
    DI
    RLC
    ANI 078H
    MOV L,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MVI H,039H
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03840H
P0_L8:
    EI
    JMP P0_L8_BODY

    ORG 00101H
P0_L8_BODY:
    MOV A,C
    RLC
    RLC
    RLC
    MOV A,A
    DI
    ANI 078H
    MOV L,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    MVI H,039H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03848H
P0_L9:
    EI
    JMP P0_L9_BODY

    ORG 00122H
P0_L9_BODY:
    MOV A,C
    RLC
    RLC
    RLC
    NOP
    MOV A,A
    DI
    ANI 078H
    MOV L,A
    MVI H,039H
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03850H
P0_L10:
    EI
    JMP P0_L10_BODY

    ORG 00144H
P0_L10_BODY:
    MOV A,C
    RLC
    RLC
    RLC
    NOP
    NOP
    MOV A,A
    DI
    ANI 078H
    MOV L,A
    MVI H,039H
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03858H
P0_L11:
    EI
    JMP P0_L11_BODY

    ORG 00165H
P0_L11_BODY:
    MOV A,C
    RLC
    RLC
    RLC
    ANI 078H
    MOV L,A
    MOV A,A
    DI
    MVI H,039H
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03860H
P0_L12:
    EI
    JMP P0_L12_BODY

    ORG 00186H
P0_L12_BODY:
    MOV A,C
    RLC
    RLC
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    RLC
    ANI 078H
    MOV L,A
    MOV A,A
    MOV A,A
    EI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MVI H,039H
    NOP
    MOV A,A
    MOV A,A
    PCHL

    ORG 03868H
P0_L13:
    EI
    JMP P0_L13_BODY

    ORG 001A7H
P0_L13_BODY:
    MOV A,C
    RLC
    RLC
    RLC
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    ANI 078H
    MOV L,A
    MOV A,A
    MOV A,A
    EI
    MVI H,039H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    NOP
    MOV A,A
    PCHL

    ORG 03870H
P0_L14:
    EI
    JMP P0_L14_BODY

    ORG 001C8H
P0_L14_BODY:
    MOV A,C
    RLC
    RLC
    RLC
    ANI 078H
    MOV L,A
    MVI H,039H
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    MOV A,A
    MOV A,A
    EI
    NOP
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    MOV A,A
    PCHL

    ORG 03820H
P0_L15:
    EI
    JMP P0_L15_BODY

    ORG 001EAH
P0_L15_BODY:
    MOV A,C
    RLC
    RLC
    RLC
    ANI 078H
    MOV L,A
    MVI H,039H
    NOP
    MOV A,A
    MOV A,A
    DI
    NOP
    MOV A,A
    MOV A,A
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    MOV A,A
    PCHL

    ORG 03900H
P1_L0:
    EI
    DI
    JMP P1_L0_BODY

    ORG 0020BH
P1_L0_BODY:
    MOV A,B
    RRC
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    DI
    ANI 078H
    MOV L,A
    MVI H,03AH
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03908H
P1_L1:
    EI
    NOP
    DI
    JMP P1_L1_BODY

    ORG 0022AH
P1_L1_BODY:
    MOV A,B
    RRC
    ANI 078H
    MOV L,A
    MVI H,03AH
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03910H
P1_L2:
    EI
    NOP
    NOP
    DI
    JMP P1_L2_BODY

    ORG 00249H
P1_L2_BODY:
    MOV A,B
    RRC
    ANI 078H
    MOV L,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    NOP
    DI
    MVI H,03AH
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03918H
P1_L3:
    EI
    NOP
    NOP
    NOP
    DI
    JMP P1_L3_BODY

    ORG 00267H
P1_L3_BODY:
    MOV A,B
    RRC
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    ANI 078H
    MOV L,A
    DI
    MVI H,03AH
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03978H
P1_L4:
    EI
    NOP
    NOP
    NOP
    NOP
    DI
    JMP P1_L4_BODY

    ORG 00284H
P1_L4_BODY:
    MOV A,B
    RRC
    ANI 078H
    MOV L,A
    MVI H,03AH
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    NOP
    NOP
    NOP
    DI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03928H
P1_L5:
    EI
    JMP P1_L5_BODY

    ORG 002A1H
P1_L5_BODY:
    MOV A,B
    MOV A,A
    DI
    RRC
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    ANI 078H
    MOV L,A
    MVI H,03AH
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03930H
P1_L6:
    EI
    JMP P1_L6_BODY

    ORG 002C1H
P1_L6_BODY:
    MOV A,B
    RRC
    MOV A,A
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    ANI 078H
    MOV L,A
    MVI H,03AH
    MOV A,A
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03938H
P1_L7:
    EI
    JMP P1_L7_BODY

    ORG 002E1H
P1_L7_BODY:
    MOV A,B
    RRC
    NOP
    MOV A,A
    DI
    ANI 078H
    MOV L,A
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MVI H,03AH
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03940H
P1_L8:
    EI
    JMP P1_L8_BODY

    ORG 00302H
P1_L8_BODY:
    MOV A,B
    RRC
    NOP
    NOP
    MOV A,A
    DI
    ANI 078H
    MOV L,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    MVI H,03AH
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03948H
P1_L9:
    EI
    JMP P1_L9_BODY

    ORG 00323H
P1_L9_BODY:
    MOV A,B
    RRC
    ANI 078H
    MOV L,A
    MOV A,A
    DI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    MVI H,03AH
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03950H
P1_L10:
    EI
    JMP P1_L10_BODY

    ORG 00344H
P1_L10_BODY:
    MOV A,B
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    RRC
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    ANI 078H
    MOV L,A
    MVI H,03AH
    MOV A,A
    MOV A,A
    PCHL

    ORG 03958H
P1_L11:
    EI
    JMP P1_L11_BODY

    ORG 00364H
P1_L11_BODY:
    MOV A,B
    RRC
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    ANI 078H
    MOV L,A
    MVI H,03AH
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03960H
P1_L12:
    EI
    JMP P1_L12_BODY

    ORG 00384H
P1_L12_BODY:
    MOV A,B
    RRC
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    ANI 078H
    MOV L,A
    NOP
    MOV A,A
    MOV A,A
    EI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MVI H,03AH
    NOP
    MOV A,A
    MOV A,A
    PCHL

    ORG 03968H
P1_L13:
    EI
    JMP P1_L13_BODY

    ORG 003A5H
P1_L13_BODY:
    MOV A,B
    RRC
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    ANI 078H
    MOV L,A
    MOV A,A
    MOV A,A
    EI
    MVI H,03AH
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    NOP
    MOV A,A
    PCHL

    ORG 03970H
P1_L14:
    EI
    JMP P1_L14_BODY

    ORG 003C6H
P1_L14_BODY:
    MOV A,B
    RRC
    ANI 078H
    MOV L,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    MOV A,A
    MOV A,A
    EI
    MVI H,03AH
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    MOV A,A
    PCHL

    ORG 03920H
P1_L15:
    EI
    JMP P1_L15_BODY

    ORG 003E7H
P1_L15_BODY:
    MOV A,B
    RRC
    ANI 078H
    MOV L,A
    MVI H,03AH
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    DI
    NOP
    MOV A,A
    MOV A,A
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    MOV A,A
    PCHL

    ORG 03A00H
P2_L0:
    EI
    DI
    JMP P2_L0_BODY

    ORG 00408H
P2_L0_BODY:
    MOV A,B
    RLC
    RLC
    RLC
    ANI 078H
    MOV L,A
    DCR E
    MOV H,D
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    DI
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03A08H
P2_L1:
    EI
    NOP
    DI
    JMP P2_L1_BODY

    ORG 00427H
P2_L1_BODY:
    MOV A,B
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    RLC
    DI
    RLC
    RLC
    ANI 078H
    MOV L,A
    DCR E
    MOV H,D
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03A10H
P2_L2:
    EI
    NOP
    NOP
    DI
    JMP P2_L2_BODY

    ORG 00445H
P2_L2_BODY:
    MOV A,B
    RLC
    RLC
    RLC
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    NOP
    DI
    ANI 078H
    MOV L,A
    DCR E
    MOV H,D
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03A18H
P2_L3:
    EI
    NOP
    NOP
    NOP
    DI
    JMP P2_L3_BODY

    ORG 00463H
P2_L3_BODY:
    MOV A,B
    RLC
    RLC
    RLC
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    ANI 078H
    MOV L,A
    DI
    DCR E
    MOV H,D
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03A78H
P2_L4:
    EI
    NOP
    NOP
    NOP
    NOP
    DI
    JMP P2_L4_BODY

    ORG 00480H
P2_L4_BODY:
    MOV A,B
    RLC
    RLC
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    RLC
    ANI 078H
    MOV L,A
    DI
    DCR E
    MOV H,D
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03A28H
P2_L5:
    EI
    JMP P2_L5_BODY

    ORG 0049CH
P2_L5_BODY:
    MOV A,B
    MOV A,A
    DI
    RLC
    RLC
    RLC
    ANI 078H
    MOV L,A
    DCR E
    MOV H,D
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03A30H
P2_L6:
    EI
    JMP P2_L6_BODY

    ORG 004BCH
P2_L6_BODY:
    MOV A,B
    RLC
    MOV A,A
    DI
    RLC
    RLC
    ANI 078H
    MOV L,A
    DCR E
    MOV H,D
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03A38H
P2_L7:
    EI
    JMP P2_L7_BODY

    ORG 004DCH
P2_L7_BODY:
    MOV A,B
    RLC
    RLC
    MOV A,A
    DI
    RLC
    ANI 078H
    MOV L,A
    DCR E
    MOV H,D
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03A40H
P2_L8:
    EI
    JMP P2_L8_BODY

    ORG 004FDH
P2_L8_BODY:
    MOV A,B
    RLC
    RLC
    RLC
    MOV A,A
    DI
    ANI 078H
    MOV L,A
    DCR E
    MOV H,D
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03A48H
P2_L9:
    EI
    JMP P2_L9_BODY

    ORG 0051EH
P2_L9_BODY:
    MOV A,B
    RLC
    RLC
    RLC
    NOP
    MOV A,A
    DI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    ANI 078H
    MOV L,A
    DCR E
    MOV H,D
    NOP
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03A50H
P2_L10:
    EI
    JMP P2_L10_BODY

    ORG 0053FH
P2_L10_BODY:
    MOV A,B
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    RLC
    RLC
    RLC
    ANI 078H
    MOV L,A
    DCR E
    MOV H,D
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03A58H
P2_L11:
    EI
    JMP P2_L11_BODY

    ORG 0055FH
P2_L11_BODY:
    MOV A,B
    RLC
    RLC
    RLC
    ANI 078H
    MOV L,A
    DCR E
    DI
    MOV H,D
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03A60H
P2_L12:
    EI
    JMP P2_L12_BODY

    ORG 0057FH
P2_L12_BODY:
    MOV A,B
    RLC
    RLC
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    RLC
    ANI 078H
    MOV L,A
    DCR E
    MOV H,D
    EI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    NOP
    NOP
    MOV A,A
    PCHL

    ORG 03A68H
P2_L13:
    EI
    JMP P2_L13_BODY

    ORG 005A0H
P2_L13_BODY:
    MOV A,B
    RLC
    RLC
    RLC
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    ANI 078H
    MOV L,A
    DCR E
    MOV H,D
    EI
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    NOP
    MOV A,A
    PCHL

    ORG 03A70H
P2_L14:
    EI
    JMP P2_L14_BODY

    ORG 005C1H
P2_L14_BODY:
    MOV A,B
    RLC
    RLC
    RLC
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    MOV A,A
    MOV A,A
    EI
    ANI 078H
    MOV L,A
    DCR E
    MOV H,D
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    MOV A,A
    PCHL

    ORG 03A20H
P2_L15:
    EI
    JMP P2_L15_BODY

    ORG 005E2H
P2_L15_BODY:
    MOV A,B
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    RLC
    MOV A,A
    MOV A,A
    EI
    RLC
    RLC
    ANI 078H
    MOV L,A
    DCR E
    MOV H,D
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    MOV A,A
    PCHL

    ORG 03B00H
P3_L0:
    EI
    DI
    JMP P3_L0_BODY

    ORG 00602H
P3_L0_BODY:
    JNZ P3_L0_WORD
    POP H
    SPHL
    POP D
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    DI
    DCR E
    JZ P3_L0_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    NOP
    NOP
    NOP
    NOP
    PCHL
P3_L0_EOF:
    LXI H,HALT
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P3_L0_WORD:
    POP B
    MOV A,C
    RRC
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    DI
    ANI 078H
    MOV L,A
    MVI H,038H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03B08H
P3_L1:
    EI
    NOP
    DI
    JMP P3_L1_BODY

    ORG 0064AH
P3_L1_BODY:
    JNZ P3_L1_WORD
    POP H
    SPHL
    POP D
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    DI
    DCR E
    JZ P3_L1_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    NOP
    NOP
    NOP
    PCHL
P3_L1_EOF:
    LXI H,HALT
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P3_L1_WORD:
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    NOP
    NOP
    NOP
    EI
    NOP
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03B10H
P3_L2:
    EI
    NOP
    NOP
    DI
    JMP P3_L2_BODY

    ORG 00690H
P3_L2_BODY:
    JNZ P3_L2_WORD
    POP H
    SPHL
    POP D
    NOP
    NOP
    NOP
    NOP
    MOV A,A
    EI
    NOP
    NOP
    DI
    DCR E
    JZ P3_L2_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    NOP
    NOP
    PCHL
P3_L2_EOF:
    LXI H,HALT
    NOP
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P3_L2_WORD:
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    NOP
    DI
    MVI H,038H
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03B18H
P3_L3:
    EI
    NOP
    NOP
    NOP
    DI
    JMP P3_L3_BODY

    ORG 006D5H
P3_L3_BODY:
    JNZ P3_L3_WORD
    POP H
    SPHL
    POP D
    NOP
    NOP
    NOP
    MOV A,A
    EI
    NOP
    NOP
    NOP
    DI
    DCR E
    JZ P3_L3_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    NOP
    PCHL
P3_L3_EOF:
    LXI H,HALT
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P3_L3_WORD:
    POP B
    MOV A,C
    RRC
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    ANI 078H
    MOV L,A
    DI
    MVI H,038H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03B78H
P3_L4:
    EI
    NOP
    NOP
    NOP
    NOP
    DI
    JMP P3_L4_BODY

    ORG 00717H
P3_L4_BODY:
    JNZ P3_L4_WORD
    POP H
    SPHL
    POP D
    NOP
    NOP
    MOV A,A
    EI
    NOP
    NOP
    NOP
    NOP
    DI
    DCR E
    JZ P3_L4_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    PCHL
P3_L4_EOF:
    LXI H,HALT
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P3_L4_WORD:
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    EI
    NOP
    NOP
    NOP
    NOP
    DI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03B28H
P3_L5:
    EI
    JMP P3_L5_BODY

    ORG 00757H
P3_L5_BODY:
    MOV A,A
    MOV A,A
    DI
    JNZ P3_L5_WORD
    POP H
    SPHL
    POP D
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    DCR E
    JZ P3_L5_EOF
    MOV A,A
    DI
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    NOP
    ORI 000H
    PCHL
P3_L5_EOF:
    MOV A,A
    DI
    LXI H,HALT
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P3_L5_WORD:
    POP B
    MOV A,C
    RRC
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    ANI 078H
    MOV L,A
    MVI H,038H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03B30H
P3_L6:
    EI
    JMP P3_L6_BODY

    ORG 0079FH
P3_L6_BODY:
    NOP
    MOV A,A
    MOV A,A
    DI
    JNZ P3_L6_WORD
    POP H
    SPHL
    POP D
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    DCR E
    JZ P3_L6_EOF
    NOP
    MOV A,A
    DI
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    ORI 000H
    PCHL
P3_L6_EOF:
    NOP
    MOV A,A
    DI
    LXI H,HALT
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P3_L6_WORD:
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    NOP
    MOV A,A
    EI
    MVI H,038H
    NOP
    NOP
    NOP
    MOV A,A
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03B38H
P3_L7:
    EI
    JMP P3_L7_BODY

    ORG 007E7H
P3_L7_BODY:
    JNZ P3_L7_WORD
    NOP
    NOP
    DI
    POP H
    SPHL
    POP D
    DCR E
    NOP
    NOP
    NOP
    NOP
    EI
    JZ P3_L7_EOF
    POP B
    NOP
    NOP
    DI
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    NOP
    NOP
    MOV A,A
    PCHL
P3_L7_EOF:
    LXI H,HALT
    NOP
    NOP
    DI
    NOP
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P3_L7_WORD:
    NOP
    NOP
    DI
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MVI H,038H
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03B40H
P3_L8:
    EI
    JMP P3_L8_BODY

    ORG 00836H
P3_L8_BODY:
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    DI
    JNZ P3_L8_WORD
    POP H
    SPHL
    POP D
    ORI 000H
    EI
    DCR E
    JZ P3_L8_EOF
    POP B
    ORI 000H
    DI
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    NOP
    MOV A,A
    PCHL
P3_L8_EOF:
    LXI H,HALT
    ORI 000H
    DI
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P3_L8_WORD:
    POP B
    MOV A,C
    RRC
    NOP
    NOP
    MOV A,A
    EI
    ANI 078H
    MOV L,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MVI H,038H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03B48H
P3_L9:
    EI
    JMP P3_L9_BODY

    ORG 0087EH
P3_L9_BODY:
    JNZ P3_L9_WORD
    NOP
    NOP
    NOP
    NOP
    DI
    POP H
    SPHL
    POP D
    NOP
    NOP
    MOV A,A
    EI
    DCR E
    JZ P3_L9_EOF
    POP B
    NOP
    ORI 000H
    DI
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    MOV A,A
    PCHL
P3_L9_EOF:
    LXI H,HALT
    NOP
    ORI 000H
    DI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P3_L9_WORD:
    NOP
    NOP
    NOP
    NOP
    DI
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    EI
    NOP
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03B50H
P3_L10:
    EI
    JMP P3_L10_BODY

    ORG 008CDH
P3_L10_BODY:
    JNZ P3_L10_WORD
    POP H
    SPHL
    MOV A,A
    DI
    POP D
    DCR E
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    JZ P3_L10_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    NOP
    DI
    MOV L,A
    MVI H,038H
    NOP
    NOP
    NOP
    MOV A,A
    PCHL
P3_L10_EOF:
    LXI H,HALT
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P3_L10_WORD:
    POP B
    MOV A,C
    MOV A,A
    DI
    RRC
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    ANI 078H
    MOV L,A
    MVI H,038H
    MOV A,A
    MOV A,A
    PCHL

    ORG 03B58H
P3_L11:
    EI
    JMP P3_L11_BODY

    ORG 00919H
P3_L11_BODY:
    JNZ P3_L11_WORD
    POP H
    SPHL
    NOP
    MOV A,A
    DI
    POP D
    DCR E
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    JZ P3_L11_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    NOP
    NOP
    DI
    MOV L,A
    MVI H,038H
    NOP
    NOP
    MOV A,A
    PCHL
P3_L11_EOF:
    LXI H,HALT
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P3_L11_WORD:
    POP B
    MOV A,C
    RRC
    MOV A,A
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    ANI 078H
    MOV L,A
    MVI H,038H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03B60H
P3_L12:
    EI
    JMP P3_L12_BODY

    ORG 00965H
P3_L12_BODY:
    JNZ P3_L12_WORD
    POP H
    SPHL
    NOP
    NOP
    MOV A,A
    DI
    POP D
    NOP
    NOP
    NOP
    NOP
    EI
    DCR E
    JZ P3_L12_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    ORI 000H
    DI
    MOV L,A
    MVI H,038H
    NOP
    MOV A,A
    PCHL
P3_L12_EOF:
    LXI H,HALT
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    NOP
    NOP
    MOV A,A
    PCHL
P3_L12_WORD:
    POP B
    MOV A,C
    RRC
    NOP
    MOV A,A
    DI
    ANI 078H
    MOV L,A
    NOP
    MOV A,A
    MOV A,A
    EI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MVI H,038H
    NOP
    MOV A,A
    MOV A,A
    PCHL

    ORG 03B68H
P3_L13:
    EI
    JMP P3_L13_BODY

    ORG 009B3H
P3_L13_BODY:
    JNZ P3_L13_WORD
    POP H
    SPHL
    POP D
    ORI 000H
    DI
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    EI
    DCR E
    JZ P3_L13_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    NOP
    ORI 000H
    DI
    MOV L,A
    MVI H,038H
    MOV A,A
    PCHL
P3_L13_EOF:
    LXI H,HALT
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    NOP
    MOV A,A
    PCHL
P3_L13_WORD:
    POP B
    MOV A,C
    RRC
    NOP
    NOP
    MOV A,A
    DI
    ANI 078H
    MOV L,A
    MOV A,A
    MOV A,A
    EI
    MVI H,038H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    NOP
    MOV A,A
    PCHL

    ORG 03B70H
P3_L14:
    EI
    JMP P3_L14_BODY

    ORG 00A01H
P3_L14_BODY:
    JNZ P3_L14_WORD
    POP H
    SPHL
    POP D
    NOP
    ORI 000H
    DI
    DCR E
    NOP
    NOP
    MOV A,A
    EI
    JZ P3_L14_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    NOP
    NOP
    DI
    NOP
    NOP
    MOV A,A
    PCHL
P3_L14_EOF:
    LXI H,HALT
    NOP
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    MOV A,A
    PCHL
P3_L14_WORD:
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MOV A,A
    DI
    NOP
    NOP
    MOV A,A
    MOV A,A
    EI
    MVI H,038H
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    MOV A,A
    PCHL

    ORG 03B20H
P3_L15:
    EI
    JMP P3_L15_BODY

    ORG 00A50H
P3_L15_BODY:
    JNZ P3_L15_WORD
    POP H
    SPHL
    POP D
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    MOV A,A
    MOV A,A
    EI
    DCR E
    JZ P3_L15_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    ORI 000H
    DI
    NOP
    MOV A,A
    PCHL
P3_L15_EOF:
    LXI H,HALT
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    MOV A,A
    PCHL
P3_L15_WORD:
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    NOP
    MOV A,A
    DI
    MVI H,038H
    ORI 000H
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    MOV A,A
    PCHL

    ORG 03C00H
P4_L0:
    EI
    DI
    JMP P4_L0_BODY

    ORG 00A9CH
P4_L0_BODY:
    JNZ P4_L0_WORD
    POP H
    SPHL
    POP D
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    DI
    DCR E
    JZ P4_L0_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    NOP
    NOP
    NOP
    NOP
    PCHL
P4_L0_EOF:
    LXI H,HALT
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P4_L0_WORD:
    MOV A,C
    RRC
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    DI
    ANI 078H
    MOV L,A
    MVI H,038H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03C08H
P4_L1:
    EI
    NOP
    DI
    JMP P4_L1_BODY

    ORG 00AE5H
P4_L1_BODY:
    JNZ P4_L1_WORD
    POP H
    SPHL
    POP D
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    DI
    DCR E
    JZ P4_L1_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    NOP
    NOP
    NOP
    PCHL
P4_L1_EOF:
    LXI H,HALT
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P4_L1_WORD:
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    EI
    NOP
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03C10H
P4_L2:
    EI
    NOP
    NOP
    DI
    JMP P4_L2_BODY

    ORG 00B2CH
P4_L2_BODY:
    JNZ P4_L2_WORD
    POP H
    SPHL
    POP D
    NOP
    NOP
    NOP
    NOP
    MOV A,A
    EI
    NOP
    NOP
    DI
    DCR E
    JZ P4_L2_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    NOP
    NOP
    PCHL
P4_L2_EOF:
    LXI H,HALT
    NOP
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P4_L2_WORD:
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    NOP
    DI
    MVI H,038H
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03C18H
P4_L3:
    EI
    NOP
    NOP
    NOP
    DI
    JMP P4_L3_BODY

    ORG 00B72H
P4_L3_BODY:
    JNZ P4_L3_WORD
    POP H
    SPHL
    POP D
    NOP
    NOP
    NOP
    MOV A,A
    EI
    NOP
    NOP
    NOP
    DI
    DCR E
    JZ P4_L3_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    NOP
    PCHL
P4_L3_EOF:
    LXI H,HALT
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P4_L3_WORD:
    MOV A,C
    RRC
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    ANI 078H
    MOV L,A
    DI
    MVI H,038H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03C78H
P4_L4:
    EI
    NOP
    NOP
    NOP
    NOP
    DI
    JMP P4_L4_BODY

    ORG 00BB5H
P4_L4_BODY:
    JNZ P4_L4_WORD
    POP H
    SPHL
    POP D
    NOP
    NOP
    MOV A,A
    EI
    NOP
    NOP
    NOP
    NOP
    DI
    DCR E
    JZ P4_L4_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    PCHL
P4_L4_EOF:
    LXI H,HALT
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P4_L4_WORD:
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    MOV A,A
    MOV A,A
    EI
    NOP
    NOP
    NOP
    NOP
    DI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03C28H
P4_L5:
    EI
    JMP P4_L5_BODY

    ORG 00BF6H
P4_L5_BODY:
    MOV A,A
    MOV A,A
    DI
    JNZ P4_L5_WORD
    POP H
    SPHL
    POP D
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    DCR E
    JZ P4_L5_EOF
    MOV A,A
    DI
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    NOP
    ORI 000H
    PCHL
P4_L5_EOF:
    MOV A,A
    DI
    LXI H,HALT
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P4_L5_WORD:
    MOV A,C
    RRC
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    ANI 078H
    MOV L,A
    MVI H,038H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03C30H
P4_L6:
    EI
    JMP P4_L6_BODY

    ORG 00C3FH
P4_L6_BODY:
    NOP
    MOV A,A
    MOV A,A
    DI
    JNZ P4_L6_WORD
    POP H
    SPHL
    POP D
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    DCR E
    JZ P4_L6_EOF
    NOP
    MOV A,A
    DI
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    ORI 000H
    PCHL
P4_L6_EOF:
    NOP
    MOV A,A
    DI
    LXI H,HALT
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P4_L6_WORD:
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    NOP
    NOP
    NOP
    EI
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03C38H
P4_L7:
    EI
    JMP P4_L7_BODY

    ORG 00C88H
P4_L7_BODY:
    JNZ P4_L7_WORD
    NOP
    NOP
    DI
    POP H
    SPHL
    POP D
    DCR E
    NOP
    NOP
    NOP
    NOP
    EI
    JZ P4_L7_EOF
    POP B
    NOP
    NOP
    DI
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    NOP
    NOP
    MOV A,A
    PCHL
P4_L7_EOF:
    LXI H,HALT
    NOP
    NOP
    DI
    NOP
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P4_L7_WORD:
    NOP
    NOP
    DI
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MVI H,038H
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03C40H
P4_L8:
    EI
    JMP P4_L8_BODY

    ORG 00CD8H
P4_L8_BODY:
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    DI
    JNZ P4_L8_WORD
    POP H
    SPHL
    POP D
    ORI 000H
    EI
    DCR E
    JZ P4_L8_EOF
    POP B
    ORI 000H
    DI
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    NOP
    MOV A,A
    PCHL
P4_L8_EOF:
    LXI H,HALT
    ORI 000H
    DI
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P4_L8_WORD:
    MOV A,C
    RRC
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    ANI 078H
    MOV L,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MVI H,038H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03C48H
P4_L9:
    EI
    JMP P4_L9_BODY

    ORG 00D21H
P4_L9_BODY:
    JNZ P4_L9_WORD
    NOP
    NOP
    NOP
    NOP
    DI
    POP H
    SPHL
    POP D
    NOP
    NOP
    MOV A,A
    EI
    DCR E
    JZ P4_L9_EOF
    POP B
    NOP
    ORI 000H
    DI
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    MOV A,A
    PCHL
P4_L9_EOF:
    LXI H,HALT
    NOP
    ORI 000H
    DI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P4_L9_WORD:
    MOV A,C
    RRC
    ANI 078H
    DI
    MOV L,A
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    MVI H,038H
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03C50H
P4_L10:
    EI
    JMP P4_L10_BODY

    ORG 00D70H
P4_L10_BODY:
    JNZ P4_L10_WORD
    POP H
    SPHL
    MOV A,A
    DI
    POP D
    DCR E
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    JZ P4_L10_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    NOP
    DI
    MOV L,A
    MVI H,038H
    NOP
    NOP
    NOP
    MOV A,A
    PCHL
P4_L10_EOF:
    LXI H,HALT
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P4_L10_WORD:
    MOV A,C
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    RRC
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    ANI 078H
    MOV L,A
    MVI H,038H
    MOV A,A
    MOV A,A
    PCHL

    ORG 03C58H
P4_L11:
    EI
    JMP P4_L11_BODY

    ORG 00DBDH
P4_L11_BODY:
    JNZ P4_L11_WORD
    POP H
    SPHL
    NOP
    MOV A,A
    DI
    POP D
    DCR E
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    JZ P4_L11_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    NOP
    NOP
    DI
    MOV L,A
    MVI H,038H
    NOP
    NOP
    MOV A,A
    PCHL
P4_L11_EOF:
    LXI H,HALT
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL
P4_L11_WORD:
    MOV A,C
    RRC
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    EI
    ANI 078H
    MOV L,A
    MVI H,038H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    PCHL

    ORG 03C60H
P4_L12:
    EI
    JMP P4_L12_BODY

    ORG 00E0AH
P4_L12_BODY:
    JNZ P4_L12_WORD
    POP H
    SPHL
    NOP
    NOP
    MOV A,A
    DI
    POP D
    NOP
    NOP
    NOP
    NOP
    EI
    DCR E
    JZ P4_L12_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    ORI 000H
    DI
    MOV L,A
    MVI H,038H
    NOP
    MOV A,A
    PCHL
P4_L12_EOF:
    LXI H,HALT
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    NOP
    NOP
    MOV A,A
    PCHL
P4_L12_WORD:
    MOV A,C
    RRC
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    ANI 078H
    MOV L,A
    NOP
    MOV A,A
    MOV A,A
    EI
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MVI H,038H
    NOP
    MOV A,A
    MOV A,A
    PCHL

    ORG 03C68H
P4_L13:
    EI
    JMP P4_L13_BODY

    ORG 00E59H
P4_L13_BODY:
    JNZ P4_L13_WORD
    POP H
    SPHL
    POP D
    ORI 000H
    DI
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    EI
    DCR E
    JZ P4_L13_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    NOP
    ORI 000H
    DI
    MOV L,A
    MVI H,038H
    MOV A,A
    PCHL
P4_L13_EOF:
    LXI H,HALT
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    NOP
    MOV A,A
    PCHL
P4_L13_WORD:
    MOV A,C
    RRC
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    ANI 078H
    MOV L,A
    MOV A,A
    MOV A,A
    EI
    MVI H,038H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    NOP
    MOV A,A
    PCHL

    ORG 03C70H
P4_L14:
    EI
    JMP P4_L14_BODY

    ORG 00EA8H
P4_L14_BODY:
    JNZ P4_L14_WORD
    POP H
    SPHL
    POP D
    NOP
    ORI 000H
    DI
    DCR E
    NOP
    NOP
    MOV A,A
    EI
    JZ P4_L14_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    NOP
    NOP
    DI
    NOP
    NOP
    MOV A,A
    PCHL
P4_L14_EOF:
    LXI H,HALT
    NOP
    NOP
    NOP
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    MOV A,A
    PCHL
P4_L14_WORD:
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    MOV A,A
    MOV A,A
    EI
    MVI H,038H
    NOP
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    NOP
    MOV A,A
    PCHL

    ORG 03C20H
P4_L15:
    EI
    JMP P4_L15_BODY

    ORG 00EF8H
P4_L15_BODY:
    JNZ P4_L15_WORD
    POP H
    SPHL
    POP D
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    MOV A,A
    MOV A,A
    EI
    DCR E
    JZ P4_L15_EOF
    POP B
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    ORI 000H
    DI
    NOP
    MOV A,A
    PCHL
P4_L15_EOF:
    LXI H,HALT
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    MOV A,A
    PCHL
P4_L15_WORD:
    MOV A,C
    RRC
    ANI 078H
    MOV L,A
    MVI H,038H
    NOP
    NOP
    NOP
    DI
    NOP
    MOV A,A
    MOV A,A
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    MOV A,A
    PCHL
