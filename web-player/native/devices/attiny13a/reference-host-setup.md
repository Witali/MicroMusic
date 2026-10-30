# Official Studio reference host: installation review

Prepared on 2026-10-30. Original packages and terms are cached and verified;
**no installer has run and no official simulator session has executed**.
This prepares an independent ATtiny13A CPU/digital/Timer0 reference. It cannot
close analog, electrical CLK/RESET or debugWIRE questions; see the
[oracle limits](simulator-oracle.md#execution-limits).

## Host observations

The user has neither MPLAB X nor its installer. Recorded official MPLAB X
downloads remain inaccessible; the SDK and update catalogs lack the base MDB
host. Prefer the documented MDB CLI when available. Studio's `atprogram` is a
programming CLI and supplies no simulator run/step operation.

The previously authorized extracted Studio launch briefly showed a window and
exited. Its cause remains unknown. Read-only inspection on 2026-10-30 found:

- No AppEnv 14.0 or Isolated Shell servicing marker in either registry view.
- The x86 VCRUNTIME140 DLL exists, version 14.51.36247.0.
- Targeted Application Error/.NET Runtime queries succeeded but found no Studio
  matches; the standard AppEnv ActivityLog was absent. This is not a diagnosis.
- The Windows Sandbox launcher is absent. No optional Windows feature was enabled.
- Computer-use inventory initializes, but browser access is disabled in Work
  settings. No tab was created and no setting changed.

Missing Shell registration motivates this next attempt; it does not prove that
installing Shell alone will make extracted Studio usable.

## Exact inputs and original terms

[The download registry](../../../../tools/downloads.json) is the authority for
canonical URLs, versions, byte counts, SHA-256, manifest members and licenses.
[The preparation report](../../../reports/reference-host-preparation-20261030.json)
references these records rather than copying their inventories.

| Registry ID | Version | Proposed use |
| --- | --- | --- |
| `microchip-studio-user-guide` | DS50002718E | Official host documentation |
| `microchip-studio-isolated-shell` | 14.0.23107.10 | Install original Shell prerequisite |
| `microchip-studio-shell-kb3095681` | 14.0.23317.0 | Install matching Shell update |
| `microchip-studio-vc2010-x86` | 10.0.30319.01 | Static review only; outside installation scope |
| `microsoft-vs2015-shell-license` | mt171552, snapshot 2026-10-30 | Original Shell terms |

The three EXEs have valid Microsoft Corporation Authenticode signatures. Sizes
and SHA-1 match the original signed Microchip bootstrap manifest; SHA-256 was
computed locally. No package has executed. Vendor binaries, terms and extracted
MSIs remain in ignored `build/`, outside Git.

Review the [original Shell terms](https://visualstudio.microsoft.com/license-terms/mt171552/)
or the [local readable text](../../../../build/reference-host-preparation-20261030/licenses/Microsoft-VS2015-Shell-License.txt).
The text is a whitespace-normalized convenience view; cached original HTML is
authoritative. The update's original
[KB3095681 terms](../../../../build/reference-host-preparation-20261030/licenses/Microsoft-KB3095681-License.htm)
were extracted unchanged from member `u76`. No terms have been accepted.

## Proposed installation scope

After explicit installation/terms approval, install only the original Shell and
KB3095681, then retry the already authorized extracted Studio GUI. This changes
system-wide shared components and registry entries. The bundle has conditional
prerequisites including VC runtimes, .NET targeting packs, MSBuild 14 and SQL
shared libraries; actual selections depend on detection.

These are legacy prerequisites. Microsoft lists the original Visual Studio 2015
release as out of support since 2017 and the product family, including Isolated
Shell, as out of support since 2025. See the
[official lifecycle](https://learn.microsoft.com/en-us/lifecycle/products/visual-studio-2015).
Selected versions come from Microchip's 7.0.2594 bootstrap; this does not establish
current Windows support or equivalence to Visual Studio 2015 Update 3.

The original bootstrap declares `/Passive /NoWeb /NoRefresh /NoRestart` for both
packages, with per-package `/Log` arguments. These are installer arguments,
not a Studio simulator CLI. They have not been executed. Keep future logs local
under `build/`; inspect and sanitize before retaining evidence. `/NoWeb` does
not prove absence of all network activity. Do not trigger an automatic restart;
report a restart requirement or stop at a failed prerequisite.

This proposal excludes the Microchip core MSI, drivers, physical programming,
firmware/fuse changes, VC2010 installation and optional Windows features.
The core MSI's read-only `WixFirewallException` table declares LocalSubnet
exceptions for AtmelStudio and atbackend; that MSI is outside this proposal.
Read-only inspection of 33 selected Shell MSIs found no firewall-named tables;
this is not a guarantee about every custom action.

Earlier permission covered launching the GUI and explicitly excluded installing
system components. Installation approval is still required. If Shell does not
suffice, record the actual failure and prepare any broader installation as a
separate reviewable change. Do not guess backend DLL APIs or register replacement
components to force a launch.

## Validation and acceptance

Verify cached packages with the offline command in the
[download setup index](../../../../docs/SETUP_DOWNLOADS.md#studio-reference-host-prerequisites-2026-10-30).
Derived records retain cabinet members, original names and hashes; source
archives and original terms remain available locally.

A future successful launch establishes only host readiness. Before retaining
reference evidence, select the actual ATtiny13A Simulator/device pack, execute
known control firmware and record host/model versions and observed state.
Studio's documented project-local debug scripting may then collect bounded
snapshots. Keep exact cycles and discrete state; the 10 ns tolerance applies
only to virtual CLK/timer/pin timestamps in verification mode. No official
result, physical measurement, real-time claim or checklist closure follows
from preparation. The plan remains **24/31 complete, seven open**.
