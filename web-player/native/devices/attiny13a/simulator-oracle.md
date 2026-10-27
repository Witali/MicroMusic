# Official ATtiny13A simulator: host acquisition audit

Updated 2026-10-27. An independent manufacturer simulator could compare Timer0/NVM/CPU
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

Acquisition and static research, 2026-10-26. The
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

1. The registered web bootstrap has now been acquired and inspected below.
   Its signed manifest identifies the separate host payloads; verify their
   registered sizes/hashes before inspecting them. A bootstrap alone is not
   an installed or runnable simulator host.
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

### Verified bootstrap acquisition and static contents

The earlier raw-HTML denial did not prevent the web reference reader from
following the official catalogue's actual web-installer link. The registered
asset `microchip-studio-web` is now cached at
`build/reference-downloads/as-installer-7.0.2594-web.exe`:

- Canonical URL: `https://ww1.microchip.com/downloads/aemDocuments/documents/DEV/ProductDocuments/SoftwareTools/as-installer-7.0.2594-web.exe`.
- Actual size: **2,333,360 bytes**; computed SHA-256:
  `bd98e452f417b03919ce232385d4d5022e1fcea9f57de86fafe934c53c117c24`.
- Windows Authenticode reports **Valid**, with Microchip Technology Incorporated
  as signer and a timestamp countersignature. No separate published checksum
  for this web installer was found; the offline installer checksum is unrelated.
- The installer was never launched. An original CAB at byte offset1,139,200,
  size1,183,685, SHA-256
  `eadcf41379a56ceb540f82d1639e2f458e48ba11cbcaf32e7c6bf8c6af8c375c`,
  was carved as data and expanded with Windows `expand.exe`. The44 flat original
  members total1,955,849 bytes. Registry `derivedAssets` links them to the installer.

The original WiX Burn manifest is
`build/microchip-studio-7.0.2594-bootstrap/ux/0` (43,284 bytes; SHA-256
`c79d2954e66a2de8054d482af8180ab203df5a72dc74f3e62e9cce521752c0e7`).
It identifies these host payloads using the official HTTPS S3 location
`https://s3-us-west-2.amazonaws.com/atmel-studio/7.0.2594/`:

| Original payload filename | Manifest bytes | Manifest SHA-1 |
| --- | ---: | --- |
| `atmelstudio-7.0.2594.msi` | 1,482,752 | `095d43a0f931cd0cc41ad4e5e874caeb26dfb472` |
| `atmelstudio-7.0.2594.7z` | 97,715,873 | `485b45535da34f9613d72b6913f4f651b122ea4b` |

Both payloads were acquired through those exact manifest URLs. Their actual
sizes and SHA-1 match the signed manifest. Locally computed SHA-256 values are
`f8ed4a616618a39f7bcc7a7b769d338d342a3f8f92f07ea01997314ffd9e0b22` (MSI) and
`75dfd5491cd27df3e9898a13e8acbd97bbdfaf248ae4092145be2bdc19429dda` (7z).
The [download registry](../../../../tools/downloads.json) pins the originals.
The archive's1895 validated relative member paths were extracted with Windows
`tar.exe` into ignored `build/microchip-studio-7.0.2594-host/`:1723 original files,
279,065,945 bytes and172 directories, with all original license/component notices.
This is not evidence that the archive is a supported portable installation.
The `ideInstaller` package is declared per-machine, with `ALLUSERS=1` and a
`TARGETDIR` property. The chain also names Visual Studio Isolated Shell2015,
VC runtimes, communication components and separate driver/toolchain/device-pack
packages. Selecting an extraction directory does not establish that those
dependencies can be omitted or that Studio supports a no-install launch. Opening
the original MSI through Windows Installer `OpenDatabase(path,0)` confirmed the
product version7.0.2594 and ALLUSERS1 without running installer/custom actions.

The manifest maps original member `u37` to `License.rtf` (94,799 bytes; SHA-256
`d2fb474bbcbe9d56abef8571cd27a7b722bae28a08d13b5000d24843ca6dfa51`);
its bytes also match the manifest SHA-1. Its EULA section1 limits installation
and internal use to developing/debugging embedded applications for supported
Microchip AVR/ARM products. Section2 restricts modification, distribution and
reverse engineering, including deriving interfaces/protocols. Section3 preserves
applicable open-source component licenses. Retain the original terms and
third-party notices locally; this inspection grants no redistribution or
undocumented simulator-ABI permission. No license acceptance dialog, installer,
driver or registration utility has been run. The only executed vendor program
was the documented `atprogram` help/usage check described below.

Reproduce the non-executing bootstrap checks:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/setup-downloads.ps1 -Id microchip-studio-web -Offline -CheckOnly
Get-AuthenticodeSignature -LiteralPath build/reference-downloads/as-installer-7.0.2594-web.exe | Select-Object Status
Get-FileHash -Algorithm SHA256 -LiteralPath build/microchip-studio-7.0.2594-bootstrap/ux/0,build/microchip-studio-7.0.2594-bootstrap/ux/u37
```

### Documented automation and remaining host step

Studio's [CLI chapter](https://onlinedocs.microchip.com/oxy/GUID-ECD8A826-B1DA-44FC-BE0B-5A53418A47BD-en-US-12/GUID-7EFC7945-0589-4C6C-9F45-C40B07349FC4.html)
documents `atprogram.exe` for programming, memory/fuse access and physical tools.
It does not establish a simulator run/step CLI. Do not substitute an assumed
`atprogram -t simulator` or reverse engineer `atbackend` commands. The documented
simulator command-file route remains MPLAB X MDB described above.

Actual extracted CLI check: from `7.0/atbackend/`, with TEMP/TMP pointing inside
the ignored bootstrap build directory, `atprogram help` exits0. The advertised
no-argument usage exits12 (no command), listing physical tools/interfaces and
device operations, with no Simulator tool or run/step command. The first help
attempt from another working directory failed to extract a CRT manifest; the
controlled local-directory retry resolved that startup issue. No device/tool
command, backend debugging session or simulator was invoked. This demonstrates
only that this documented help command runs locally; it does not establish a
headless simulator API or readiness of the Studio GUI.

Studio does document [debug scripting](https://onlinedocs.microchip.com/oxy/GUID-ECD8A826-B1DA-44FC-BE0B-5A53418A47BD-en-US-12/GUID-E6AEB04E-0C45-43E6-AB02-33AC01E3A513.html):
place project-local `debughooks.py` beside the ELF or project, defining all four
callbacks `should_process_breakpoint`, `has_processed_breakpoint`, `on_reset`
and `on_eval_expr`. The IDE loads it in IronPython2.7/.NET at session launch.
Documented `studio_interface` methods include `ReadMemory`, `CalcNumericValue`
and `Print`; this could collect bounded firmware snapshots at breakpoints.
It is an IDE-hosted API, not a standalone simulator host. A later capture must
first establish its actual memory-space names, device/pack compatibility and
unmodified control execution through the supported Simulator selection.

Next: establish the supported GUI/Isolated Shell dependencies and a real
ATtiny13A Simulator session; the host payload extraction is complete. Do not
execute MSI custom actions or an administrative installation merely to extract
files. Unless a supported portable route is established, the documented
execution option is an isolated Windows installation/VM with Studio's GUI and
project-local scripting. No such installation or simulator session exists here.

2026-10-27 launch observation: after explicit user approval, Windows app control
launched the extracted `7.0/AtmelStudio.exe` (531,688 bytes; SHA-256
`21229ec4471897be90dbdbe90a37896821e7d44afc6bd0832d70430195d79f42`).
It briefly returned one Studio window; that handle disappeared before state
capture, and a process check then found zero Studio processes. Application-log
inspection was denied, so the termination cause is unknown. The user stopped
computer control with Escape; no further UI action followed. No installer,
driver or simulator session was run. A missing conventional installation or
Shell InstallDir value is not enough to assign a failure cause.

The user then explicitly requested console commands when available. Prefer the
documented MDB command-file route for future reference execution and record its
actual host/device/pack readiness before comparing results. Studio's successful
programming-CLI help does not supply a simulator stepping command. Do not retry
an unchanged denied installer URL or substitute guessed backend commands.

### Execution limits

Studio's manufacturer documentation says
[analog peripherals are absent and NVM modeling is incomplete](https://onlinedocs.microchip.com/oxy/GUID-19BA5E18-FC0D-4489-9A99-3E3FFC279F4D-en-US-1/GUID-0FF41858-E8B2-4ED9-A242-5913E0AE9922.html).
Its [stimulus delays](https://onlinedocs.microchip.com/oxy/GUID-19BA5E18-FC0D-4489-9A99-3E3FFC279F4D-en-US-1/GUID-63392F42-9853-4C4A-B5D2-CBFC8E5A3ADD.html)
are evaluated between CPU single-steps and can overrun a requested delay during
a multicycle instruction. Thus Studio is a supported candidate for independent
CPU/digital/Timer0 comparisons, not an analog reference or proof of our
half-edge/1 ps asynchronous timing. Actual ATtiny13A model results and its exact
usable peripheral subset remain unmeasured. **No official simulator session has
been executed.**

## Archived MDB host availability

The [official MPLAB archive](https://www.microchip.com/en-us/tools-resources/archives/mplab-ecosystem)
also links Windows IDE **6.25**, matching the acquired SDK. Its exact href was
registered before the local network check as `mplab-x-ide-windows-6.25` in
`plannedAssets`. On 2026-10-27 the web reader followed it to the manufacturer's
access-denied page, and an ordinary HTTPS HEAD with permitted network access
returned **403 Forbidden**. No GET, complete/partial installer or active download
exists. No published checksum was obtained; 6.35's checksum is not applicable.

This alternative did not establish an executable MDB host. Prefer the documented
console route when it becomes available; do not repeat the unchanged denied URL,
infer simulator commands from Studio's programming CLI, or treat the unexecuted
command-file template as verification evidence.

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

## debugWIRE admission remains separate

The read-only DWEN audit does not justify lifting the
[unsupported-mode guard](interfaces.md). In the pinned
[DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf),
debugWIRE is section15; section16 is self-programming. Section15.3 requires
programmed DWEN and unprogrammed lock bits, describes PB5's open-drain/pull-up
gateway and preserves CKSEL. Section15.5 excludes external RESET and keeps
unspecified clock circuitry active in every sleep mode. It supplies neither a
complete unattended cold-start contract nor the exact sleep gates/wake phases.
Table10-4's PB5 overrides also depend on RSTDISBL; section17.1/Table17-2 retain
conflicting locked-device statements. Absence of an attached debugger does not
establish ordinary PB5 RESET behavior or disable fuse-enabled OCD.

The pinned [AVR instruction manual DS40002198A](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf),
section5.13, makes BREAK stop an enabled, unlocked OCD target; debugger absence
is not an exemption. Host `debugEnabled` remains a diagnostic fixture. DWDR's
current zero read is also a fixture, not a documented absent-debugger guarantee.
Official [Atmel-ICE guidance](https://onlinedocs.microchip.com/oxy/GUID-DDB0017E-84E3-4E77-AAE9-7AC4290E5E8B-en-US-4/GUID-F9465218-A270-4DF1-995F-D5293CE87DD8.html)
confirms DWEN activation requires a power toggle and recommends unprogrammed
RSTDISBL/lock bits, but does not complete that passive contract. Keep all DWEN
configurations rejected and the plan item open; no wire protocol or external
programming implementation is inferred from these sources or simulator files.
