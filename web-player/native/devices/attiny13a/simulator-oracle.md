# Official ATtiny13A simulator: host acquisition audit

2026-10-26. An independent manufacturer simulator could compare Timer0/NVM/CPU
behavior with this project. No official simulator session has been executed.
Simulator agreement would remain software evidence, not a silicon measurement
or closure of the hardware-dependent plan items.

## Verified SDK result

The [official SDK archive index](https://ww1.microchip.com/downloads/mplab/x/sdk/archive.html)
links `mplab-x-sdk-v6.25.zip`. Its downloaded size is **111,698,606 bytes** and
locally computed SHA-256 is
`6f78c110804ff8e6ec53265ff79a508a907a74a31c37fdc3c5c7c9678bc3e2f6`.
This is not a separately published vendor checksum. URL, destination, purpose
and license are pinned in [`tools/downloads.json`](../../../../tools/downloads.json),
ID `mplab-x-sdk`; the archive stays in ignored `build/reference-downloads/`.

The actual archive contains **zero `.jar` and zero `.class` files**. Its
runtime-like binaries belong to bundled test fixtures/device packs, not a
standalone MDBCore host. The Gallery package description mentioning precompiled
libraries therefore does not establish that this SDK alone runs the simulator.

Relevant original archive members:

- `mplab-x-sdk/index.html`: SDK version and warning that device files are separate.
- `mplab-x-sdk/MPLAB_X/doc/MDBCore.htm`: “What else is needed?” requires an
  MPLAB X installation; its documented API supports Java 8 and warns that later
  versions may not work. This does not establish the Java requirement of a newer IDE.
- `mplab-x-sdk/MPLAB_X/doc/mdbcs.html`: libraries/classpath come from the IDE;
  `packslibs.packsfolder` selects a relocated pack directory, and third-party
  native libraries have separate installation dependencies.
- `mplab-x-sdk/MPLAB_X/mdbcs/utils/getcp.py`: official classpath construction example.
- `mplab-x-sdk/MPLAB_X/sample/debug_API/program_device/src/programdevice/Main.java`:
  official Java application example, dependent on those libraries.
- `mplab-x-sdk/MPLAB_X/doc/mchp-software-license.txt`: source copyright/usage notice.
  Bundled third-party and device-pack notices apply separately.

Eight selected original members, including development/build instructions, are
retained byte-for-byte under `build/mplab-sdk-6.25/`; `derivedAssets` in the registry
records all member names. No SDK code or example was compiled/executed. Local
Java/Javac are Temurin 25.0.3; compatibility with the documented API is unproven.
No MDB command or usual MPLAB X/Microchip Studio installation was found.

Reproduce the archive checks from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/setup-downloads.ps1 -Id mplab-x-sdk -Offline -CheckOnly
python -c "from zipfile import ZipFile; z=ZipFile('build/reference-downloads/mplab-x-sdk-v6.25.zip'); print({e:sum(n.endswith(e) for n in z.namelist()) for e in ('.jar','.class')}); print(z.read('mplab-x-sdk/MPLAB_X/doc/mchp-software-license.txt').decode('cp1252'))"
```

## Supported host route and next step

[Microchip documents MDB](https://developerhelp.microchip.com/xwiki/bin/view/software-tools/ides/x/debugging/mdb/)
as a scriptable CLI installed with MPLAB X IDE. The
[MDB User's Guide DS50002102K](https://ww1.microchip.com/downloads/aemDocuments/documents/DEV/ProductDocuments/UserGuides/MDB-User-Guide.pdf)
documents command files, `device`, `hwtool SIM`, pack selection, `program`,
`stepi`, SFR inspection and memory examination. Its `program` command here would
load the software simulator only; no physical chip/programmer is involved.

The [official IDE page](https://www.microchip.com/en-us/tools-resources/develop/mplab-x-ide)
currently publishes **6.35**, dated 2026-07-24, with this Windows installer link:

`https://ww1.microchip.com/downloads/aemDocuments/documents/DEV/ProductDocuments/SoftwareTools/MPLABX-v6.35-windows-installer.exe`

Its Windows row's published `data-shasum` is
`64a5247d5c1e2db7c6fb3b8d2fa43d5578d7efebe2e51db44706b20d441c2061`.
Both href and full checksum were read from that row in the in-app browser;
the installer was **not downloaded**. Raw HTTP HEAD returned 403, so no installer
byte count or local file is asserted. The temporary research tab was closed.

The later normal GET was also denied and no final/partial file was created;
that attempt is recorded in `plannedAssets` and
[`SETUP_DOWNLOADS.md`](../../../../docs/SETUP_DOWNLOADS.md). No unchanged blocked
installer request was retried during the Studio research below.

Next: register acquisition of this host distribution, verify its published hash,
inspect its license and installer/help or documented extraction options, and
establish whether a workspace-local host is supported. Keep drivers, global
installation and physical tool access outside that step. Use the host's supported
Java/runtime libraries rather than assuming the existing Java 25 is compatible.
Then select the pinned ATtiny_DFP **3.4.278** through the vendor-supported pack
mechanism and confirm `device ATtiny13A`, `pack`, and `hwtool SIM` actually work.
The SDK does not prove that an arbitrary relocated pack or native DLL ABI works.

The guide's page22/Table3-6 explicitly documents `pack [version]`; the version
must already be available to the selected device. Availability and compatibility
of this ATtiny_DFP version remain unverified until the host actually reports them.
An unexecuted smoke-command template after acquiring the host and pack:

```text
device ATtiny13A
pack 3.4.278
hwtool SIM
program "<absolute-path-to-control-variable-top-3.elf>"
reset
stepi 2000
print TCNT0
print TCCR0A
print TIFR0
quit
```

The project already assembles that nonzero control under
`build/timer0-probe-verification/`; first establish reset, device geometry,
instruction counts and known nonzero timer behavior before trying TOP=0.
Instruction-boundary inspection alone cannot verify subinstruction bus phases.

## Additional supported host route: Microchip Studio

Read-only research, 2026-10-26. The
[official Studio page](https://www.microchip.com/en-us/tools-resources/develop/microchip-studio)
publishes archived **7.0.2594**, dated 2022-06-20, with offline and web installers.
Microchip discourages it for new designs; its legacy AVR simulator remains
relevant to this existing device. The
[installation guide](https://onlinedocs.microchip.com/oxy/GUID-ECD8A826-B1DA-44FC-BE0B-5A53418A47BD-en-US-12/GUID-8F63ECC8-08B9-4CCD-85EF-88D30AC06499.html)
describes a web bootstrap below 10 MB and a self-contained offline installer,
Windows x86/x64 support and 6 GB installation space. These are documented
requirements, not measured sizes or a verified portable distribution.

The already verified **ATtiny_DFP 3.4.278** archive contains an explicit Studio
mapping in `Microchip.ATtiny_DFP.pdsc`, under device `Dname="ATtiny13A"`,
`environment name="atmel"`:

| Manufacturer metadata | Value |
| --- | --- |
| Tool ID | `com.atmel.avrdbg.tool.simulator` |
| `com.atmel.avrdbg.tool.simulator.key` | `ATtiny13A` |
| `com.atmel.avrdbg.tool.simulator.model.win32` | `simulator/win32/libattiny13a.dll` |

This proves that the pack advertises the ATtiny13A simulator to Studio, beyond
merely including a DLL. Archive provenance, license and exact hashes remain in
the [download registry](../../../../tools/downloads.json) and
[retained manufacturer provenance](../../../vendor/microchip/ATtiny_DFP/3.4.278/README.md).
It does not prove that Studio 7.0.2594 has accepted this newer pack or executed it.

The documented execution route, not performed here:

1. Obtain and register a Studio installer from that official page, verify its
   full checksum and inspect its license. The web bootstrap is a smaller
   acquisition candidate; all additional payloads would also need registration.
2. Use the supported Windows installation, preferably isolated in a VM for
   reference work. The [official FAQ](https://onlinedocs.microchip.com/oxy/GUID-ECD8A826-B1DA-44FC-BE0B-5A53418A47BD-en-US-12/GUID-54DCACE0-2AB9-4CCE-B17B-403ECC49B3B5.html)
   explicitly supports simulator use in a VM. This is a documented isolation
   option, not evidence of a portable/no-install host or an existing local VM.
3. In [Tools > Device Pack Manager](https://onlinedocs.microchip.com/oxy/GUID-ECD8A826-B1DA-44FC-BE0B-5A53418A47BD-en-US-12/GUID-16828780-2386-4670-B6A2-C516B2156E05.html),
   use Browse pack file for the pinned `.atpack`; confirm the selected version
   and that ATtiny13A/Simulator are actually available, then restart Studio as
   directed. Record any incompatibility rather than substituting a device.
4. [Open Object File For Debugging](https://onlinedocs.microchip.com/oxy/GUID-ECD8A826-B1DA-44FC-BE0B-5A53418A47BD-en-US-12/GUID-48DCA42B-F694-4A3C-8A9B-43B5FF34C32D.html),
   select ATtiny13A and Simulator in the object project's Tool settings. Studio's
   [ELF/DWARF support](https://onlinedocs.microchip.com/oxy/GUID-ECD8A826-B1DA-44FC-BE0B-5A53418A47BD-en-US-12/GUID-0A5C8A7E-FFD4-4442-A77B-C782712558BE.html)
   documents DWARF2. Static inspection found no `.debug*` sections in the current
   `build/timer0-probe-verification/control-variable-top-3.elf`; prepare a separate
   DWARF2 build when source-level inspection is needed. No probe was rebuilt here.
5. Run known nonzero controls before TOP=0 experiments. Record firmware bytes,
   pack/model/host identities, instruction/cycle counter, SFR observations and
   actual clock/fuse settings. The [session guide](https://onlinedocs.microchip.com/oxy/GUID-19BA5E18-FC0D-4489-9A99-3E3FFC279F4D-en-US-1/GUID-AF25F327-93D4-4CDE-813E-CAC4C37B143B.html)
   documents cycle counting and reset behavior. Treat fuses as session state:
   [simulator defaults](https://onlinedocs.microchip.com/oxy/GUID-19BA5E18-FC0D-4489-9A99-3E3FFC279F4D-en-US-1/GUID-0FF41858-E8B2-4ED9-A242-5913E0AE9922.html)
   can differ from physical factory defaults, including CKDIV8 and SELFPRGEN.
   The manufacturer's [known issues](https://onlinedocs.microchip.com/oxy/GUID-19BA5E18-FC0D-4489-9A99-3E3FFC279F4D-en-US-1/GUID-05DABC65-1D8E-4A0F-8957-24FBC9732E79.html)
   include fuse-related session aborts; confirm each needed setting in the
   running host instead of assuming that every profile is configurable.

### Verified access state and limits

The official catalogue is readable through the web reference reader. A new,
read-only raw-HTML request for the Studio page was denied; current browser
inventory was empty. The canonical bootstrap binary URL and full checksum have
therefore **not been resolved**. No guessed filename, bootstrap, offline package,
installer execution, system change or new dependency was used. There is no live
download handle. Next acquisition requires resolving the actual official link
and registering it first; the MPLAB X denial does not prove that this different
bootstrap URL is denied.

Studio's manufacturer documentation says
[analog peripherals are absent and NVM modeling is incomplete](https://onlinedocs.microchip.com/oxy/GUID-19BA5E18-FC0D-4489-9A99-3E3FFC279F4D-en-US-1/GUID-0FF41858-E8B2-4ED9-A242-5913E0AE9922.html).
Its [stimulus delays](https://onlinedocs.microchip.com/oxy/GUID-19BA5E18-FC0D-4489-9A99-3E3FFC279F4D-en-US-1/GUID-63392F42-9853-4C4A-B5D2-CBFC8E5A3ADD.html)
are evaluated between CPU single-steps and can overrun a requested delay during
a multicycle instruction. Thus Studio is a supported candidate for independent
CPU/digital/Timer0 comparisons, not an analog reference or proof of our
half-edge/1 ps asynchronous timing. Actual ATtiny13A model results and its exact
usable peripheral subset remain unmeasured. **No official simulator session has
been executed.**

## Oracle limits

The official MPLAB X [debug feature matrix](https://ww1.microchip.com/downloads/aemDocuments/documents/DEV/ProductDocuments/SupportingCollateral/SimDebugFeatures.pdf)
lists ATtiny13A. The [peripheral matrix](https://ww1.microchip.com/downloads/aemDocuments/documents/DEV/ProductDocuments/SupportingCollateral/SimPeripheralSupport.pdf)
lists NVMController, PORTB, TC0 and WDT for it; ADC, comparator and external
interrupt entries are blank. The matrix warns that implementation is not
stringent peripheral testing. It cannot serve as a full analog, clock-receiver,
RESET-electrical or debugWIRE oracle.
These MPLAB X matrices do not establish a complete Studio peripheral contract;
keep the two host configurations and their observed results separate.

The pinned DFP's `simulator/win32/libattiny13a.dll` and dependencies are already
registered local extractions. Their factory/version exports and `interface=dw`
metadata do not document a callable simulator or debugWIRE wire protocol.
No guessed factory signature, vtable or wire command has been invoked.
