; Intel 8080: CRC16/0x0007 + CRC16/0x0009 in ONE 64-KiB ROM pass
; No RAM, stack writes, CALL/RET or lookup tables.
; CRC-16 state (0x0007) in BC, (0x0009) in DE; zero initial values.
; SP is *read-only pointer*, initially FFFFh.  POP PSW retrieves the byte
; at (SP+1) into A, DCX SP yields SP += 1 net. Flag byte is overwritten.
; HL: H scratch, L 8-bit byte counter. On L rollover (every 256 bytes),
; obtain next address via HL = SP + 1 and stop only at 0000h.
; Use composite 32-bit footer at FFFCh-FFFFh for both CRCs to be zero.
        ORG 0000H
        DI
        LXI SP,0FFFFH
        XRA A
        MOV B,A
        MOV C,A
        MOV D,A
        MOV E,A
        MOV L,A

NEXT:   POP PSW      ; A=ROM[(SP+1)&FFFFh], SP=SP+2 (ROM is read only)
        DCX SP       ; SP is now SP+1 (one new ROM byte per iteration)
        XRA B        ; A=t1 = byte XOR CRC_0007.high
        MOV H,A      ; preserve t1 to reuse when CRC_0007.high is overwritten
        XRA B        ; recover original byte
        XRA D        ; t2 = byte XOR CRC_0009.high
        MOV D,A      ; D=t2; keep t1 in H; B is free as scratch

        ; CRC-16 polynomial 0x0007: low=t ^ (t<<1) ^ (t<<2)
        ; high=old_low ^ (t>>7) ^ (t>>6)
        MOV A,H      ; H=t1 remains intact throughout CRC_0007 update
        RLC
        RLC
        ANI 003H     ; t1>>6, clears CY for RAR
        MOV B,A      ; temporary Gray-code input q=t1>>6
        RAR          ; q>>1, zero enters highest bit
        XRA B        ; (t1>>6) XOR (t1>>7)
        XRA C        ; CRC_0007 new high
        MOV B,A      ; update CRC_0007.high
        MOV A,H      ; t1
        ADD A        ; t1<<1
        XRA H        ; t1 XOR (t1<<1)
        ADD A        ; (t1<<1) XOR (t1<<2)
        XRA H        ; CRC_0007 new low
        MOV C,A      ; update CRC_0007.low

        ; CRC-16 polynomial 0x0009: low=t ^ (t<<3)
        ; high=old_low ^ (t>>5)
        MOV A,D
        RLC
        RLC
        RLC
        MOV H,A      ; rotl3(t2)
        ANI 007H     ; t2>>5
        XRA E        ; new high
        MOV E,A      ; temporarily in E
        MOV A,H
        ANI 0F8H     ; (t2<<3)&0xFF
        XRA D        ; new low
        MOV D,E      ; new high -> D
        MOV E,A      ; new low -> E

        INR L        ; count bytes modulo 256
        JNZ NEXT
        ; Only once per 256 bytes, test if the next ROM address is zero.
        LXI H,0001H  ; next ROM address is SP+1
        DAD SP       ; carry iff SP==FFFF after 65536 bytes
        JNC NEXT     ; HL low returns to 0 at each 256-byte boundary

        ; Both residues must be zero.
        MOV A,B
        ORA C
        ORA D
        ORA E
        JNZ FAIL
        EI           ; success -> INTE=1
FAIL:   HLT          ; failure -> INTE remains 0
