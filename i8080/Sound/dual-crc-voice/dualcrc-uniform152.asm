; Intel 8080, uniform 152T PWM, 3.5 MHz, 16 levels.
; Baseline diagnostics/ramp and DPCM words: original-manifest.json.
; INTE changes at EI/DI completion; no READY, INT must stay low.
; Build complete ROM: python build.py; data/tables/footers: manifest.
; Only ROM reads through SP; no CALL/PUSH or memory writes.

    ORG 01100H
VOICE:
    DI
    LXI SP,STREAM
    MVI D,020H
    MVI E,0F0H
    MVI H,01CH
    POP B
    JMP PHASE_0
AFTER_4:
    JZ DONE
    POP B
    NOP
PHASE_0:
    MOV A,C
    RLC
    RLC
    ANA H
    ADD E
    ADD D
    MOV D,A
    MOV L,A
    PCHL
AFTER_0:
    MOV A,A
    NOP
    NOP
    NOP
    NOP
PHASE_1:
    MOV A,C
    RRC
    ANA H
    ADD E
    ADD D
    MOV D,A
    ORI 040H
    MOV L,A
    PCHL
AFTER_1:
PHASE_2:
    MOV A,B
    RRC
    MOV A,C
    RAR
    RRC
    RRC
    RRC
    ANA H
    ADD E
    ADD D
    MOV D,A
    ORI 080H
    MOV L,A
    PCHL
AFTER_2:
    MOV A,A
    NOP
    NOP
    NOP
    NOP
PHASE_3:
    MOV A,B
    RLC
    ANA H
    ADD E
    ADD D
    MOV D,A
    ORI 0C0H
    MOV L,A
    PCHL
AFTER_3:
    JM PHASE_4_LINK
    MVI A,000H
PHASE_4:
    MOV A,B
    RRC
    RRC
    ANA H
    ADD E
    ADD D
    MOV D,A
    MVI H,01DH
    MOV L,A
    PCHL
PHASE_4_LINK:
    MVI A,000H
    MOV A,B
    RRC
    RRC
    ANA H
    ADD E
    ADD D
    MOV D,A
    MVI H,01EH
    MOV L,A
    PCHL
DONE:
    DI
    HLT

    ORG 01200H
WIDTH_0_0:
    EI
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
    JMP AFTER_0

    ORG 01211H
WIDTH_0_1:
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
    NOP
    NOP
    NOP
    NOP
    JMP AFTER_0

    ORG 01223H
WIDTH_0_2:
    EI
    NOP
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
    NOP
    NOP
    NOP
    JMP AFTER_0

    ORG 01235H
WIDTH_0_3:
    EI
    NOP
    NOP
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
    NOP
    NOP
    JMP AFTER_0

    ORG 01247H
WIDTH_0_4:
    EI
    NOP
    NOP
    NOP
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
    NOP
    JMP AFTER_0

    ORG 01259H
WIDTH_0_5:
    EI
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
    JMP AFTER_0

    ORG 0126AH
WIDTH_0_6:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    JMP AFTER_0

    ORG 0127CH
WIDTH_0_7:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    JMP AFTER_0

    ORG 0128EH
WIDTH_0_8:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    JMP AFTER_0

    ORG 012A0H
WIDTH_0_9:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    JMP AFTER_0

    ORG 012B2H
WIDTH_0_10:
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
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    JMP AFTER_0

    ORG 012C3H
WIDTH_0_11:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    DI
    NOP
    NOP
    NOP
    NOP
    JMP AFTER_0

    ORG 012D5H
WIDTH_0_12:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    DI
    NOP
    NOP
    NOP
    JMP AFTER_0

    ORG 012E7H
WIDTH_0_13:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    DI
    NOP
    NOP
    JMP AFTER_0

    ORG 012F9H
WIDTH_0_14:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    DI
    NOP
    JMP AFTER_0

    ORG 0130BH
WIDTH_0_15:
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
    JMP AFTER_0

    ORG 0131CH
WIDTH_1_0:
    EI
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
    JMP AFTER_1

    ORG 0132DH
WIDTH_1_1:
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
    NOP
    NOP
    NOP
    NOP
    JMP AFTER_1

    ORG 0133FH
WIDTH_1_2:
    EI
    NOP
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
    NOP
    NOP
    NOP
    JMP AFTER_1

    ORG 01351H
WIDTH_1_3:
    EI
    NOP
    NOP
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
    NOP
    NOP
    JMP AFTER_1

    ORG 01363H
WIDTH_1_4:
    EI
    NOP
    NOP
    NOP
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
    NOP
    JMP AFTER_1

    ORG 01375H
WIDTH_1_5:
    EI
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
    JMP AFTER_1

    ORG 01386H
WIDTH_1_6:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    JMP AFTER_1

    ORG 01398H
WIDTH_1_7:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    JMP AFTER_1

    ORG 013AAH
WIDTH_1_8:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    JMP AFTER_1

    ORG 013BCH
WIDTH_1_9:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    JMP AFTER_1

    ORG 013CEH
WIDTH_1_10:
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
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    JMP AFTER_1

    ORG 013DFH
WIDTH_1_11:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    DI
    NOP
    NOP
    NOP
    NOP
    JMP AFTER_1

    ORG 013F1H
WIDTH_1_12:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    DI
    NOP
    NOP
    NOP
    JMP AFTER_1

    ORG 01403H
WIDTH_1_13:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    DI
    NOP
    NOP
    JMP AFTER_1

    ORG 01415H
WIDTH_1_14:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    DI
    NOP
    JMP AFTER_1

    ORG 01427H
WIDTH_1_15:
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
    JMP AFTER_1

    ORG 01438H
WIDTH_2_0:
    EI
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
    JMP AFTER_2

    ORG 01449H
WIDTH_2_1:
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
    NOP
    NOP
    NOP
    NOP
    JMP AFTER_2

    ORG 0145BH
WIDTH_2_2:
    EI
    NOP
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
    NOP
    NOP
    NOP
    JMP AFTER_2

    ORG 0146DH
WIDTH_2_3:
    EI
    NOP
    NOP
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
    NOP
    NOP
    JMP AFTER_2

    ORG 0147FH
WIDTH_2_4:
    EI
    NOP
    NOP
    NOP
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
    NOP
    JMP AFTER_2

    ORG 01491H
WIDTH_2_5:
    EI
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
    JMP AFTER_2

    ORG 014A2H
WIDTH_2_6:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    JMP AFTER_2

    ORG 014B4H
WIDTH_2_7:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    JMP AFTER_2

    ORG 014C6H
WIDTH_2_8:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    JMP AFTER_2

    ORG 014D8H
WIDTH_2_9:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    DI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    JMP AFTER_2

    ORG 014EAH
WIDTH_2_10:
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
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    JMP AFTER_2

    ORG 014FBH
WIDTH_2_11:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    DI
    NOP
    NOP
    NOP
    NOP
    JMP AFTER_2

    ORG 0150DH
WIDTH_2_12:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    DI
    NOP
    NOP
    NOP
    JMP AFTER_2

    ORG 0151FH
WIDTH_2_13:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    DI
    NOP
    NOP
    JMP AFTER_2

    ORG 01531H
WIDTH_2_14:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    DI
    NOP
    JMP AFTER_2

    ORG 01543H
WIDTH_2_15:
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
    JMP AFTER_2

    ORG 01554H
WIDTH_3_0:
    EI
    DI
    MOV A,D
    ORA B
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    JMP AFTER_3

    ORG 01566H
WIDTH_3_1:
    EI
    NOP
    DI
    MOV A,D
    ORA B
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    JMP AFTER_3

    ORG 01578H
WIDTH_3_2:
    EI
    NOP
    NOP
    DI
    MOV A,D
    ORA B
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    JMP AFTER_3

    ORG 0158AH
WIDTH_3_3:
    EI
    NOP
    NOP
    NOP
    DI
    MOV A,D
    ORA B
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    JMP AFTER_3

    ORG 0159CH
WIDTH_3_4:
    EI
    NOP
    NOP
    NOP
    NOP
    DI
    MOV A,D
    ORA B
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    JMP AFTER_3

    ORG 015AEH
WIDTH_3_5:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MOV A,D
    ORA B
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    JMP AFTER_3

    ORG 015C0H
WIDTH_3_6:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    DI
    MOV A,D
    ORA B
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    JMP AFTER_3

    ORG 015D2H
WIDTH_3_7:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    DI
    MOV A,D
    ORA B
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    JMP AFTER_3

    ORG 015E4H
WIDTH_3_8:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    DI
    MOV A,D
    ORA B
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    JMP AFTER_3

    ORG 015F6H
WIDTH_3_9:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    DI
    MOV A,D
    ORA B
    MOV A,A
    MOV A,A
    MOV A,A
    JMP AFTER_3

    ORG 01608H
WIDTH_3_10:
    EI
    MOV A,D
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    ORA B
    NOP
    NOP
    NOP
    NOP
    JMP AFTER_3

    ORG 0161AH
WIDTH_3_11:
    EI
    MOV A,D
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    DI
    ORA B
    NOP
    NOP
    NOP
    JMP AFTER_3

    ORG 0162CH
WIDTH_3_12:
    EI
    MOV A,D
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    DI
    ORA B
    NOP
    NOP
    JMP AFTER_3

    ORG 0163EH
WIDTH_3_13:
    EI
    MOV A,D
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    DI
    ORA B
    NOP
    JMP AFTER_3

    ORG 01650H
WIDTH_3_14:
    EI
    MOV A,D
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    DI
    ORA B
    JMP AFTER_3

    ORG 01662H
WIDTH_3_15:
    EI
    MOV A,D
    ORA B
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    DI
    JMP AFTER_3

    ORG 01674H
WIDTH_4_0:
    EI
    DI
    DCR H
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
    JMP AFTER_4

    ORG 01685H
WIDTH_4_1:
    EI
    NOP
    DI
    DCR H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    JMP AFTER_4

    ORG 01697H
WIDTH_4_2:
    EI
    NOP
    NOP
    DI
    DCR H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    JMP AFTER_4

    ORG 016A9H
WIDTH_4_3:
    EI
    NOP
    NOP
    NOP
    DI
    DCR H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    JMP AFTER_4

    ORG 016BBH
WIDTH_4_4:
    EI
    NOP
    NOP
    NOP
    NOP
    DI
    DCR H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    JMP AFTER_4

    ORG 016CDH
WIDTH_4_5:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    DCR H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    JMP AFTER_4

    ORG 016DEH
WIDTH_4_6:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    DI
    DCR H
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    JMP AFTER_4

    ORG 016F0H
WIDTH_4_7:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    DI
    DCR H
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    JMP AFTER_4

    ORG 01702H
WIDTH_4_8:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    DI
    DCR H
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    JMP AFTER_4

    ORG 01714H
WIDTH_4_9:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    DI
    DCR H
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    JMP AFTER_4

    ORG 01726H
WIDTH_4_10:
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
    DCR H
    MOV A,A
    MOV A,A
    MOV A,A
    JMP AFTER_4

    ORG 01737H
WIDTH_4_11:
    EI
    DCR H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    DI
    NOP
    NOP
    NOP
    NOP
    JMP AFTER_4

    ORG 01749H
WIDTH_4_12:
    EI
    DCR H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    DI
    NOP
    NOP
    NOP
    JMP AFTER_4

    ORG 0175BH
WIDTH_4_13:
    EI
    DCR H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    DI
    NOP
    NOP
    JMP AFTER_4

    ORG 0176DH
WIDTH_4_14:
    EI
    DCR H
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    DI
    NOP
    JMP AFTER_4

    ORG 0177FH
WIDTH_4_15:
    EI
    DCR H
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
    JMP AFTER_4

    ORG 01790H
WIDTH_5_0:
    EI
    DI
    POP H
    SPHL
    MOV A,H
    ORA L
    MVI H,01CH
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    JMP AFTER_4

    ORG 017A1H
WIDTH_5_1:
    EI
    NOP
    DI
    POP H
    SPHL
    MOV A,H
    ORA L
    MVI H,01CH
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    JMP AFTER_4

    ORG 017B2H
WIDTH_5_2:
    EI
    NOP
    NOP
    DI
    POP H
    SPHL
    MOV A,H
    ORA L
    MVI H,01CH
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    JMP AFTER_4

    ORG 017C4H
WIDTH_5_3:
    EI
    NOP
    NOP
    NOP
    DI
    POP H
    SPHL
    MOV A,H
    ORA L
    MVI H,01CH
    MOV A,A
    NOP
    NOP
    NOP
    JMP AFTER_4

    ORG 017D6H
WIDTH_5_4:
    EI
    NOP
    NOP
    NOP
    NOP
    DI
    POP H
    SPHL
    MOV A,H
    ORA L
    MVI H,01CH
    MOV A,A
    NOP
    NOP
    JMP AFTER_4

    ORG 017E8H
WIDTH_5_5:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    POP H
    SPHL
    MOV A,H
    ORA L
    MVI H,01CH
    MOV A,A
    NOP
    JMP AFTER_4

    ORG 017F9H
WIDTH_5_6:
    EI
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    DI
    POP H
    SPHL
    MOV A,H
    ORA L
    MVI H,01CH
    MOV A,A
    JMP AFTER_4

    ORG 0180AH
WIDTH_5_7:
    EI
    POP H
    SPHL
    MOV A,A
    NOP
    NOP
    DI
    MOV A,H
    ORA L
    MVI H,01CH
    NOP
    NOP
    NOP
    NOP
    JMP AFTER_4

    ORG 0181CH
WIDTH_5_8:
    EI
    POP H
    SPHL
    MOV A,A
    NOP
    NOP
    NOP
    DI
    MOV A,H
    ORA L
    MVI H,01CH
    NOP
    NOP
    NOP
    JMP AFTER_4

    ORG 0182EH
WIDTH_5_9:
    EI
    POP H
    SPHL
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    DI
    MOV A,H
    ORA L
    MVI H,01CH
    NOP
    NOP
    JMP AFTER_4

    ORG 01840H
WIDTH_5_10:
    EI
    POP H
    SPHL
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    MOV A,H
    ORA L
    MVI H,01CH
    NOP
    JMP AFTER_4

    ORG 01851H
WIDTH_5_11:
    EI
    POP H
    SPHL
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    DI
    MOV A,H
    ORA L
    MVI H,01CH
    JMP AFTER_4

    ORG 01862H
WIDTH_5_12:
    EI
    POP H
    SPHL
    MOV A,H
    ORA L
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    DI
    MVI H,01CH
    MOV A,A
    JMP AFTER_4

    ORG 01873H
WIDTH_5_13:
    EI
    POP H
    SPHL
    MOV A,H
    ORA L
    MVI H,01CH
    MOV A,A
    NOP
    NOP
    NOP
    NOP
    DI
    NOP
    NOP
    JMP AFTER_4

    ORG 01885H
WIDTH_5_14:
    EI
    POP H
    SPHL
    MOV A,H
    ORA L
    MVI H,01CH
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    DI
    NOP
    JMP AFTER_4

    ORG 01896H
WIDTH_5_15:
    EI
    POP H
    SPHL
    MOV A,H
    ORA L
    MVI H,01CH
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    MOV A,A
    NOP
    DI
    JMP AFTER_4
