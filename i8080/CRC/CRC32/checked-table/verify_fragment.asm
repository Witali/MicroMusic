; --------------------------------------------------------------
; VERIFY_TABLE: deterministic, table-independent integrity test.
; The CRC32C table occupies pages 0100h, 0200h, 0300h, 0400h.
; At address (page<<8 | index), the page supplies one byte
; of reflected table[index], in little-endian CRC byte order.
;
; Let T[i] be a 32-bit entry and S(x)=(x>>1)^(x&1?POLY:0).
; Check T[0]=0, T[1]=F26B8303h and, for i=1..127:
;      T[2*i+1] == T[2*i] XOR T[1]
;      S(T[2*i])  == T[i].
; S is invertible because top bit of POLY is set. These
; equalities uniquely determine all 256 table entries.
; NO TABLE used to validate the TABLE. No RAM, no stack.
; --------------------------------------------------------------
        ORG 0500H
VERIFY_TABLE:
        LXI H,0100H        ; Compare all four bytes of T[0] to zero
        MOV A,M
        INR H
        ORA M
        INR H
        ORA M
        INR H
        ORA M
        JNZ STOP

        LXI H,0101H        ; Check T[1] = F26B8303h
        MOV A,M
        CPI 03H
        JNZ STOP
        INR H
        MOV A,M
        CPI 083H
        JNZ STOP
        INR H
        MOV A,M
        CPI 06BH
        JNZ STOP
        INR H
        MOV A,M
        CPI 0F2H
        JNZ STOP

        LXI H,0102H        ; L = 2*i, initially i=1; H=plane
CHECK_PAIR:
        MOV E,M            ; x = T[2*i], lowest byte
        INR L              ; -> T[2*i+1]
        MOV A,E
        XRI 03H            ; x.low ^ T[1].low
        CMP M
        JNZ STOP
        DCR L
        INR H
        MOV D,M
        INR L
        MOV A,D
        XRI 083H
        CMP M
        JNZ STOP
        DCR L
        INR H
        MOV C,M
        INR L
        MOV A,C
        XRI 06BH
        CMP M
        JNZ STOP
        DCR L
        INR H
        MOV B,M
        INR L
        MOV A,B
        XRI 0F2H
        CMP M
        JNZ STOP
        DCR L              ; L is even again, = 2*i

        MOV A,B            ; shift 32-bit B:C:D:E right by one
        ORA A              ; zero CY
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
        JNC NO_POLY        ; CY = original low bit of T[2*i]
        XRI 078H           ; reflected polynomial 82F63B78h
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
NO_POLY:
        MOV A,L
        RRC                ; even 2*i -> i
        MOV L,A
        MVI H,01H
        MOV A,E            ; test S(T[2*i]) == T[i]
        CMP M
        JNZ STOP
        INR H
        MOV A,D
        CMP M
        JNZ STOP
        INR H
        MOV A,C
        CMP M
        JNZ STOP
        INR H
        MOV A,B
        CMP M
        JNZ STOP

        MOV A,L            ; i -> 2*(i+1) modulo 256
        RLC
        ADI 02H
        MOV L,A
        MVI H,01H          ; return to lowest byte plane for next pair
        JNZ CHECK_PAIR     ; when L wraps to zero, i=127 done
        JMP CRC_START      ; verified: now full-ROM CRC using LUT
