; INTEL 8080, ROM-only CRC-32C self-test, exact 1-KiB table precheck.
; No RAM, no CALL/RET/PUSH, SP reads ROM only through POP H.
; 0000h: startup -> 0500h table self-test, independent of table values
; 0100h-04FFh: 4 x 256 byte-planes of standard CRC-32C lookup table
; 0500h: verifier (checks ALL 1024 table bytes mathematically)
; Entire [0000h,ENDROM) is checked after table passes verification.
; Last four bytes store pre-xor raw CRC32C of [0000h,ENDROM-4)
; in little-endian order, yielding RAW CRC32C(full ROM)=00000000h.
; A=not a result; CPU halts with INTE=1 pass, INTE=0 fail.
; NOTE: keep INTR low; EI+HLT with active interrupts is unsafe without RAM.
        ORG 0000H
RESET:  DI
        JMP VERIFY_TABLE

CRC_START:
        LXI SP,0000H      ; SP is read-only ROM address pointer
        LXI B,0FFFFH      ; CRC highest 16 bits: B:C
        LXI D,0FFFFH      ; CRC lowest 16 bits: D:E
NEXT4:  POP H            ; 2 ROM bytes (L,H), SP += 2
        MOV A,E
        XRA L
        MOV E,A
        MOV A,D
        XRA H
        MOV D,A
        POP H            ; 2 more ROM bytes
        MOV A,C
        XRA L
        MOV C,A
        MOV A,B
        XRA H
        MOV B,A

; Four table rounds per four source bytes, each time CRC=(CRC>>8)^T[E].
        MOV L,E           ; index = CRC low byte
        MVI H,01H         ; byte plane #0
        MOV A,D
        XRA M
        MOV E,A
        INR H             ; byte plane #1
        MOV A,C
        XRA M
        MOV D,A
        INR H             ; byte plane #2
        MOV A,B
        XRA M
        MOV C,A
        INR H             ; byte plane #3
        MOV B,M

        MOV L,E           ; index = CRC low byte
        MVI H,01H         ; byte plane #0
        MOV A,D
        XRA M
        MOV E,A
        INR H             ; byte plane #1
        MOV A,C
        XRA M
        MOV D,A
        INR H             ; byte plane #2
        MOV A,B
        XRA M
        MOV C,A
        INR H             ; byte plane #3
        MOV B,M

        MOV L,E           ; index = CRC low byte
        MVI H,01H         ; byte plane #0
        MOV A,D
        XRA M
        MOV E,A
        INR H             ; byte plane #1
        MOV A,C
        XRA M
        MOV D,A
        INR H             ; byte plane #2
        MOV A,B
        XRA M
        MOV C,A
        INR H             ; byte plane #3
        MOV B,M

        MOV L,E           ; index = CRC low byte
        MVI H,01H         ; byte plane #0
        MOV A,D
        XRA M
        MOV E,A
        INR H             ; byte plane #1
        MOV A,C
        XRA M
        MOV D,A
        INR H             ; byte plane #2
        MOV A,B
        XRA M
        MOV C,A
        INR H             ; byte plane #3
        MOV B,M
        LXI H,0000H      ; HL := SP
        DAD SP
        MOV A,H
        CPI 80H         ; address end after all 4-byte blocks
        JNZ NEXT4
        MOV A,B           ; raw residue must equal zero
        ORA C
        ORA D
        ORA E
        JNZ STOP
        EI                ; success: assert INTE, do not take interrupts
STOP:   HLT               ; fail: DI from RESET remains in effect

        ORG 0100H
; CRC-32C table byte plane 0 of 4 (standard reflected poly 82F63B78h)
        DB 00H,03H,F7H,F4H,1FH,1CH,E8H,EBH,CFH,CCH,38H,3BH,D0H,D3H,27H,24H
        DB 6FH,6CH,98H,9BH,70H,73H,87H,84H,A0H,A3H,57H,54H,BFH,BCH,48H,4BH
        DB DEH,DDH,29H,2AH,C1H,C2H,36H,35H,11H,12H,E6H,E5H,0EH,0DH,F9H,FAH
        DB B1H,B2H,46H,45H,AEH,ADH,59H,5AH,7EH,7DH,89H,8AH,61H,62H,96H,95H
        DB BCH,BFH,4BH,48H,A3H,A0H,54H,57H,73H,70H,84H,87H,6CH,6FH,9BH,98H
        DB D3H,D0H,24H,27H,CCH,CFH,3BH,38H,1CH,1FH,EBH,E8H,03H,00H,F4H,F7H
        DB 62H,61H,95H,96H,7DH,7EH,8AH,89H,ADH,AEH,5AH,59H,B2H,B1H,45H,46H
        DB 0DH,0EH,FAH,F9H,12H,11H,E5H,E6H,C2H,C1H,35H,36H,DDH,DEH,2AH,29H
        DB 78H,7BH,8FH,8CH,67H,64H,90H,93H,B7H,B4H,40H,43H,A8H,ABH,5FH,5CH
        DB 17H,14H,E0H,E3H,08H,0BH,FFH,FCH,D8H,DBH,2FH,2CH,C7H,C4H,30H,33H
        DB A6H,A5H,51H,52H,B9H,BAH,4EH,4DH,69H,6AH,9EH,9DH,76H,75H,81H,82H
        DB C9H,CAH,3EH,3DH,D6H,D5H,21H,22H,06H,05H,F1H,F2H,19H,1AH,EEH,EDH
        DB C4H,C7H,33H,30H,DBH,D8H,2CH,2FH,0BH,08H,FCH,FFH,14H,17H,E3H,E0H
        DB ABH,A8H,5CH,5FH,B4H,B7H,43H,40H,64H,67H,93H,90H,7BH,78H,8CH,8FH
        DB 1AH,19H,EDH,EEH,05H,06H,F2H,F1H,D5H,D6H,22H,21H,CAH,C9H,3DH,3EH
        DB 75H,76H,82H,81H,6AH,69H,9DH,9EH,BAH,B9H,4DH,4EH,A5H,A6H,52H,51H

        ORG 0200H
; CRC-32C table byte plane 1 of 4 (standard reflected poly 82F63B78h)
        DB 00H,83H,70H,F3H,97H,14H,E7H,64H,58H,DBH,28H,ABH,CFH,4CH,BFH,3CH
        DB C7H,44H,B7H,34H,50H,D3H,20H,A3H,9FH,1CH,EFH,6CH,08H,8BH,78H,FBH
        DB 8EH,0DH,FEH,7DH,19H,9AH,69H,EAH,D6H,55H,A6H,25H,41H,C2H,31H,B2H
        DB 49H,CAH,39H,BAH,DEH,5DH,AEH,2DH,11H,92H,61H,E2H,86H,05H,F6H,75H
        DB 1DH,9EH,6DH,EEH,8AH,09H,FAH,79H,45H,C6H,35H,B6H,D2H,51H,A2H,21H
        DB DAH,59H,AAH,29H,4DH,CEH,3DH,BEH,82H,01H,F2H,71H,15H,96H,65H,E6H
        DB 93H,10H,E3H,60H,04H,87H,74H,F7H,CBH,48H,BBH,38H,5CH,DFH,2CH,AFH
        DB 54H,D7H,24H,A7H,C3H,40H,B3H,30H,0CH,8FH,7CH,FFH,9BH,18H,EBH,68H
        DB 3BH,B8H,4BH,C8H,ACH,2FH,DCH,5FH,63H,E0H,13H,90H,F4H,77H,84H,07H
        DB FCH,7FH,8CH,0FH,6BH,E8H,1BH,98H,A4H,27H,D4H,57H,33H,B0H,43H,C0H
        DB B5H,36H,C5H,46H,22H,A1H,52H,D1H,EDH,6EH,9DH,1EH,7AH,F9H,0AH,89H
        DB 72H,F1H,02H,81H,E5H,66H,95H,16H,2AH,A9H,5AH,D9H,BDH,3EH,CDH,4EH
        DB 26H,A5H,56H,D5H,B1H,32H,C1H,42H,7EH,FDH,0EH,8DH,E9H,6AH,99H,1AH
        DB E1H,62H,91H,12H,76H,F5H,06H,85H,B9H,3AH,C9H,4AH,2EH,ADH,5EH,DDH
        DB A8H,2BH,D8H,5BH,3FH,BCH,4FH,CCH,F0H,73H,80H,03H,67H,E4H,17H,94H
        DB 6FH,ECH,1FH,9CH,F8H,7BH,88H,0BH,37H,B4H,47H,C4H,A0H,23H,D0H,53H

        ORG 0300H
; CRC-32C table byte plane 2 of 4 (standard reflected poly 82F63B78h)
        DB 00H,6BH,3BH,50H,9AH,F1H,A1H,CAH,D9H,B2H,E2H,89H,43H,28H,78H,13H
        DB 5EH,35H,65H,0EH,C4H,AFH,FFH,94H,87H,ECH,BCH,D7H,1DH,76H,26H,4DH
        DB BDH,D6H,86H,EDH,27H,4CH,1CH,77H,64H,0FH,5FH,34H,FEH,95H,C5H,AEH
        DB E3H,88H,D8H,B3H,79H,12H,42H,29H,3AH,51H,01H,6AH,A0H,CBH,9BH,F0H
        DB 7BH,10H,40H,2BH,E1H,8AH,DAH,B1H,A2H,C9H,99H,F2H,38H,53H,03H,68H
        DB 25H,4EH,1EH,75H,BFH,D4H,84H,EFH,FCH,97H,C7H,ACH,66H,0DH,5DH,36H
        DB C6H,ADH,FDH,96H,5CH,37H,67H,0CH,1FH,74H,24H,4FH,85H,EEH,BEH,D5H
        DB 98H,F3H,A3H,C8H,02H,69H,39H,52H,41H,2AH,7AH,11H,DBH,B0H,E0H,8BH
        DB F6H,9DH,CDH,A6H,6CH,07H,57H,3CH,2FH,44H,14H,7FH,B5H,DEH,8EH,E5H
        DB A8H,C3H,93H,F8H,32H,59H,09H,62H,71H,1AH,4AH,21H,EBH,80H,D0H,BBH
        DB 4BH,20H,70H,1BH,D1H,BAH,EAH,81H,92H,F9H,A9H,C2H,08H,63H,33H,58H
        DB 15H,7EH,2EH,45H,8FH,E4H,B4H,DFH,CCH,A7H,F7H,9CH,56H,3DH,6DH,06H
        DB 8DH,E6H,B6H,DDH,17H,7CH,2CH,47H,54H,3FH,6FH,04H,CEH,A5H,F5H,9EH
        DB D3H,B8H,E8H,83H,49H,22H,72H,19H,0AH,61H,31H,5AH,90H,FBH,ABH,C0H
        DB 30H,5BH,0BH,60H,AAH,C1H,91H,FAH,E9H,82H,D2H,B9H,73H,18H,48H,23H
        DB 6EH,05H,55H,3EH,F4H,9FH,CFH,A4H,B7H,DCH,8CH,E7H,2DH,46H,16H,7DH

        ORG 0400H
; CRC-32C table byte plane 3 of 4 (standard reflected poly 82F63B78h)
        DB 00H,F2H,E1H,13H,C7H,35H,26H,D4H,8AH,78H,6BH,99H,4DH,BFH,ACH,5EH
        DB 10H,E2H,F1H,03H,D7H,25H,36H,C4H,9AH,68H,7BH,89H,5DH,AFH,BCH,4EH
        DB 20H,D2H,C1H,33H,E7H,15H,06H,F4H,AAH,58H,4BH,B9H,6DH,9FH,8CH,7EH
        DB 30H,C2H,D1H,23H,F7H,05H,16H,E4H,BAH,48H,5BH,A9H,7DH,8FH,9CH,6EH
        DB 41H,B3H,A0H,52H,86H,74H,67H,95H,CBH,39H,2AH,D8H,0CH,FEH,EDH,1FH
        DB 51H,A3H,B0H,42H,96H,64H,77H,85H,DBH,29H,3AH,C8H,1CH,EEH,FDH,0FH
        DB 61H,93H,80H,72H,A6H,54H,47H,B5H,EBH,19H,0AH,F8H,2CH,DEH,CDH,3FH
        DB 71H,83H,90H,62H,B6H,44H,57H,A5H,FBH,09H,1AH,E8H,3CH,CEH,DDH,2FH
        DB 82H,70H,63H,91H,45H,B7H,A4H,56H,08H,FAH,E9H,1BH,CFH,3DH,2EH,DCH
        DB 92H,60H,73H,81H,55H,A7H,B4H,46H,18H,EAH,F9H,0BH,DFH,2DH,3EH,CCH
        DB A2H,50H,43H,B1H,65H,97H,84H,76H,28H,DAH,C9H,3BH,EFH,1DH,0EH,FCH
        DB B2H,40H,53H,A1H,75H,87H,94H,66H,38H,CAH,D9H,2BH,FFH,0DH,1EH,ECH
        DB C3H,31H,22H,D0H,04H,F6H,E5H,17H,49H,BBH,A8H,5AH,8EH,7CH,6FH,9DH
        DB D3H,21H,32H,C0H,14H,E6H,F5H,07H,59H,ABH,B8H,4AH,9EH,6CH,7FH,8DH
        DB E3H,11H,02H,F0H,24H,D6H,C5H,37H,69H,9BH,88H,7AH,AEH,5CH,4FH,BDH
        DB F3H,01H,12H,E0H,34H,C6H,D5H,27H,79H,8BH,98H,6AH,BEH,4CH,5FH,ADH

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


        ORG 7FFCH
CRC_FIXUP: DB 0FFH,0FFH,0FFH,0FFH ; replaced by build.py
        END
