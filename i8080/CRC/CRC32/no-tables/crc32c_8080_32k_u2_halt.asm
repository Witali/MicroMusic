; TABLELESS STANDARD CRC-32C (Castagnoli reflected 82F63B78h)
; Intel 8080 only, no RAM and no writes; SP reads ROM via POP H.
; Entire ROM [0000h,END) incl four-byte raw-CRC trailer has residue 0.
; Init=FFFFFFFF, xorout=FFFFFFFF for CRC-32C (test: 123456789 -> E3069283).
; BEWARE: EI+HLT success indication relies on INTE high after EI;
;          keep INTR inactive. A corrupt program may fail to execute.
        ORG 0000H
        DI
        LXI SP,0000H
        LXI B,0FFFFH
        LXI D,0FFFFH
NEXT4:  POP H             ; Caution: POP reads 2 bytes of ROM using SP
        MOV A,E
        XRA L
        MOV E,A
        MOV A,D
        XRA H
        MOV D,A
        POP H
        MOV A,C
        XRA L
        MOV C,A
        MOV A,B
        XRA H             ; XRA clears CY, also for first RAR
        MOV B,A
        LXI H,8010H    ; H=bias high byte, L=iteration count
BITLOOP:
        MOV A,B
        RAR
        MOV B,A
        MOV A,C
        RAR
        MOV C,A
        MOV A,D
        RAR
        MOV D,A
        MOV A,E
        RAR
        MOV E,A
        JNC NOXOR0
        XRI 078H      ; A already contains the shifted E
        MOV E,A
        MOV A,D
        XRI 03BH
        MOV D,A
        MOV A,C
        XRI 0F6H
        MOV C,A
        MOV A,B
        XRI 082H
        MOV B,A
NOXOR0:
        MOV A,B
        RAR
        MOV B,A
        MOV A,C
        RAR
        MOV C,A
        MOV A,D
        RAR
        MOV D,A
        MOV A,E
        RAR
        MOV E,A
        JNC NOXOR1
        XRI 078H      ; A already contains the shifted E
        MOV E,A
        MOV A,D
        XRI 03BH
        MOV D,A
        MOV A,C
        XRI 0F6H
        MOV C,A
        MOV A,B
        XRI 082H
        MOV B,A
NOXOR1:
        DCR L             ; does not alter CY
        JNZ BITLOOP
        DAD SP            ; carry iff SP >= ROM end address
        JNC NEXT4
        MOV A,B
        ORA C
        ORA D
        ORA E
        JNZ FAIL
        EI                ; success INTE high
FAIL:   HLT               ; stop; fail leaves INTE low
        ORG 7FFCH
FIXUP:  DB 0FFH,0FFH,0FFH,0FFH
        END
