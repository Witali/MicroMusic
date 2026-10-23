# Agent handoff — Intel 8080 table-free ROM CRC integrity checker

Read `README_START_HERE_RU.md`, `DEVELOPMENT_HISTORY_RU.md` and `TECHNICAL_SPEC_RU.md` first. This bundle combines all significant research milestones, source code, tests, and benchmark CSVs. Slightly different intermediate drafts and nested historical ZIP files have been pruned; original executable research directories remain runnable.

**Target**: Intel 8080, ROM-only computer (no RAM/writable stack), full 64 KiB address space; historical clock 3.5 MHz. Software uses original 8080 opcodes only, performs no RAM writes and no lookup-table access. Hardware test for A15 and INTE remains outstanding.

**Selected algorithms:** CRC-16 MSB-first, init=0, xorout=0, non-reflected, generator `G1=0x10025` and `G2=0x10047`; product over GF(2) `0x1006209BB`, abbreviated `0x006209BB`. Append big-endian 32-bit remainder over the first 65532 ROM bytes to FFFC..FFFF. Both CRC16 remainders over the entire ROM must be zero. This is not standard ZIP CRC-32 or Castagnoli.

**Key binaries (in `SELECTED_FIRMWARE/`):**

| Firmware | Program bytes | T-states/ROM byte | Full 64KiB at 3.5 MHz |
|---|---:|---:|---:|
| `milestone_dual_0025_0047_min42.bin` | 42 | 766.002 | 14.343 s |
| `milestone_dual_0025_0047_min41_RESET.bin` | 41 | 766.002 | 14.343 s |
| `milestone_dual_0025_0047_mid57.bin` | 57 | 586.002 | 10.973 s |
| `milestone_dual_0025_0047_fast75.bin` | 75 | 288.118 | 5.395 s |
| `milestone_dual_0025_0047_fast82.bin` | 82 | 279.118 | 5.226 s |

The reset-only build omits `DI`; use it only immediately after a true hardware RESET. Success is `EI; HLT` (INTE asserted); failure `HLT` with INTE clear. Real hardware interrupt behavior needs validation.

**Best size optimization**: shared bit-at-a-time CRC kernel with only 9 bytes of assembled code, in `research/10_pair_0025_0047_v6_minimal/Intel8080_DualCRC16_v6/asm/bitwise_shared_parity.asm`. Formula uses `DAD H` (shift), `SBB A` (0x00/0xFF carry mask), `ANA C` (select polynomial low byte), and parity flag `JPE` to transition from 0x25 to 0x47 after a passing first run. This version is significantly slower than byte-parallel forms; never claim size reduction implies speedup.

**Reliability**: detects all 1/2/3-bit errors on 64 KiB, all odd-weight error masks (G1 contains x+1), and bursts up to 32 bits. A known undetected 4-bit mask spans 3921 bits (exponents 0,1065,1278,3920). It is not cryptographic and is not an address-bus test. CRC32C has better local four-bit detection by the measured span criterion but is slower in our 8080 implementation. Be explicit about what was measured vs proved.

**How to reproduce**:
```
cd research/10_pair_0025_0047_v6_minimal/Intel8080_DualCRC16_v6
python3 tools/verify_and_build.py
cc -O3 -std=c11 tests/test_compact.c -o test_compact
./test_compact bin/bitwise_shared_parity.bin
```

Fast v5 source/math regression:
```
cd research/09_pair_0025_0047_v5_fast/Intel8080_DualCRC16_0025_0047_v5
python3 tests/verify_sources_and_math.py
```

Further research priorities: find 45–60-byte implementations materially faster than 766T/byte while preserving both polynomials; instruction-level superoptimization with flag/carry correctness; alternative register layouts for fused two-CRC processing; pair selection based on physical error models; independent startup integrity checks if corruption of the verifier is a real safety concern; actual 8080 hardware verification. Keep every candidate verified by independent bitwise reference, whole-ROM execution, address trace, fault injection, and exact T-state accounting.

**Important**: Prior software validation, even hundreds of successful whole-ROM test runs, does not imply real Intel 8080 electrical validation. This bundle is an engineering handoff, not a claim of certified safety.
