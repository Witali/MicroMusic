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

## Oracle limits

The official [debug feature matrix](https://ww1.microchip.com/downloads/aemDocuments/documents/DEV/ProductDocuments/SupportingCollateral/SimDebugFeatures.pdf)
lists ATtiny13A. The [peripheral matrix](https://ww1.microchip.com/downloads/aemDocuments/documents/DEV/ProductDocuments/SupportingCollateral/SimPeripheralSupport.pdf)
lists NVMController, PORTB, TC0 and WDT for it; ADC, comparator and external
interrupt entries are blank. The matrix warns that implementation is not
stringent peripheral testing. It cannot serve as a full analog, clock-receiver,
RESET-electrical or debugWIRE oracle.

The pinned DFP's `simulator/win32/libattiny13a.dll` and dependencies are already
registered local extractions. Their factory/version exports and `interface=dw`
metadata do not document a callable simulator or debugWIRE wire protocol.
No guessed factory signature, vtable or wire command has been invoked.
