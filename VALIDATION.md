# Validation

## KiCad 10 reorganization

- The active project now uses only KiCad 10 native files: seven schematics with format `20260306` and the unchanged PCB with format `20260206`.
- KiCad 10.0.7 successfully exports the complete root hierarchy to `kit-bt-amp-22v-complete-schematics.pdf`: seven non-empty pages, including all six child sheets.
- KiCad 10.0.7 exports `validation/netlist-kicad10.xml` with **274 components and 304 nets**, matching the original 10.99 conversion. `validation/netlist-kicad10.net` is also included.
- The schematics retain embedded symbol definitions. Obsolete 10.99 external `.kicad_sym` files and their library tables are no longer part of the active project.
- The earlier 10.99 validation results below are retained as historical conversion diagnostics.

## Native-file and hierarchy checks

- `kit-bt-amp-22v.kicad_pro`, root `kit-bt-amp-22v.kicad_sch`, six child `.kicad_sch` sheets, and `kit-bt-amp-22v.kicad_pcb` exist as native KiCad files.
- KiCad 10.99.0 successfully exported the complete root hierarchy to a seven-page A3 PDF and an XML netlist (274 components, 304 nets), and ran ERC. The root links all six expected sheets; Konnect reports no sheet-pin mismatches.
- KiCad 10.0.7 successfully imported the PCB, exported its GLB with embedded models, and ran DRC. The board has 278 footprints, 222 declared signal nets plus the unconnected pseudo-net, four copper layers, and 87 embedded 3-D model references.

These checks establish that the converted files parse and export. They do **not** establish electrical or manufacturing correctness.

## Conversion diagnostics retained, not hidden

### ERC

Final full-hierarchy ERC: **1,047 findings (39 errors, 1,008 warnings)**.

| Finding | Count |
|---|---:|
| Off-grid endpoints | 519 |
| Footprint-link issues | 280 |
| Embedded/library-symbol mismatches | 133 |
| Isolated pin labels | 66 |
| Power pins not driven | 32 |
| Unconnected wire endpoints | 6 |
| Pins not driven | 6 |
| Multiple net names | 4 |
| Unannotated item reported by ERC | 1 |

The XML netlist nevertheless includes the reported `C0A` item without a question mark. Most findings are native-import/library/linkage and source-grid issues. No attempt was made to conceal them by changing ERC severities or rewriting connectivity.

### DRC

Full PCB DRC: **1,710 findings (1,202 errors, 508 warnings)**, with **0 unconnected items** and no schematic-parity test selected.

| Finding | Count |
|---|---:|
| Clearance | 499 |
| Solder-mask bridges | 199 |
| Track width | 199 |
| Drill out of range | 199 |
| Silk over copper | 199 |
| Library-footprint issues | 199 |
| Silk overlap | 53 |
| Copper edge clearance | 41 |
| Via diameter | 29 |
| Hole clearance | 27 |
| Dangling tracks | 24 |
| Padstack | 18 |
| Silk edge clearance | 12 |
| Shorting items | 6 |
| Courtyard overlaps | 3 |
| Text height | 2 |
| Copper sliver | 1 |

The large repeated groups are consistent with Altium import and ruleset/library differences. The original routing and layout were preserved rather than silently modified to make the counts look better. This conversion is **not DRC-clean** and should be reviewed before fabrication.

## No-silkscreen revision

### Removed and hidden items

Konnect `delete_graphics` dry-runs matched **13 `F.SilkS`** and **2,705 `B.SilkS`** board-level items. Both were applied, and verification dry-runs then matched zero. A backup was kept under the ignored `conversion/pre-no-silk/` directory. One scoped byte-range edit (without whole-file re-serialization) then removed **300 footprint-internal `F.SilkS` expressions**:

- 268 `fp_line`
- 29 `fp_circle`
- 3 `fp_text user` (two on U8, one on J_PVDD)
- No footprint-internal `B.SilkS` graphics remained after the board-level deletion.

Total deleted silk graphics: **3,018** (2,718 board-level + 300 footprint-internal). No `fp_arc`, `fp_poly`, `fp_rect`, or `fp_curve` deletions were needed.

No property blocks were deleted. **222 previously visible Reference properties were hidden**; another **330 properties were already hidden** (274 Value + 56 Reference). All 552 remaining silk-layered property blocks are now hidden. The newly hidden references are four unnamed mounting-hole footprints plus:

```text
C0A C0B C1 C1A C1B C2 C3 C4 C5 C6 C7 C8 C9 C10 C11 C12 C13 C14 C15 C16
C17 C18 C19 C20 C21 C22 C23 C24 C25 C26 C27 C28 C29 C30 C31 C32 C33 C34
C35 C36 C37 C38 C39 C41 C45 C48 C66 C68 C69 C70 C71 C72 C73 C74 C76 C78
C79 C80 C82 CAVDD0 CCDC CCREF CF0A0 CF0A1 CF0B0 CF0B1 CF1A0 CF1A1 CF1B0
CF1B1 CFDC CFGD CGD0 CGD0N0 CGD0N1 CGD1 CGD1N0 CGD1N1 CIN1 CIN2 CIN3
CIN4 CSUP1 CSUP2 CSUP3 CSUP4 CT8 CVGDC D1 D2 D3 D4 DS1 DS2 DS3 DS4 DS5
DVDD0 J1 J2 J4 J_BCK_3V3 J_BCK_5V J_PVDD J_USB1 J_VCC_PSOC L0A L0B L1
L1A L1B L2 L3 L4 L5 L6 L7 L8 L9 L10 L11 LSUP P2 P4 P6 P7 P_L2 Q1 Q2 Q3
R1 R2 R3 R4 R5 R6 R7 R9 R11 R12 R14 R16 R17 R18 R22 R23 R25 R26 R27 R28
R29 R30 R31 R32 R33 R34 R35 R37 R38 R40 R41 R42 R44 R45 R46 R47 R51 R52
R53 R54 R55 R56 R59 R61 R62 R63 R64 R65 R66 R67 R68 R69 R74 R79 R80 R81
R82 R83 R85 R86 R89 R90 R93 R94 R96 R112 R114 R115 R116 R117 R131 R132
R134 RT1 RT8 SW1 SW3 SW_BT_RES SW_RECOVER SW_RES TP_BTVDDIN U1 U2 U3 U4
U5 U7 U8
```

The 556 remaining `SilkS` strings in the native PCB are only four layer/stackup declarations and the 552 hidden property layer fields. There are no remaining silk graphics or visible silk-layered properties, and no `SilkS` references in the native schematics, project, or symbol-library table.

### Structural and validation comparison

- Footprints: **278 → 278**
- Pads: **951 → 951**
- Nets including the unconnected pseudo-net: **223 → 223**
- Embedded 3-D model references: **87 → 87**
- Tracks/vias: **4,016 → 4,016**
- Zones: **9 → 9**
- UUIDs removed: **3,018**, all belonging to deleted silk items; UUIDs added or otherwise changed: **0**
- Both retained `Merus` metadata strings are unchanged.
- ERC is unchanged at **1,047 findings (39 errors, 1,008 warnings)**. The schematic hierarchy still exports a seven-page PDF and the same XML netlist (274 components, 304 nets); component and net connectivity comparison is identical.
- DRC changed from **1,710 (1,202 errors, 508 warnings) to 1,444 (1,202 errors, 242 warnings)** findings. The only category changes are `silk_overlap` 53→0, `silk_over_copper` 199→0, `silk_edge_clearance` 12→0, and `text_height` 2→0. All other DRC categories, including all 1,202 errors, remain unchanged; unconnected items remain 0. This is still **not a fabrication-ready conversion**.
- Full GLB export succeeds after silk removal.

## Header stand-in placement correction

The first no-silk render exposed a render-only placement defect: `header()` put each plastic body at the footprint origin, which is pin 1 for these imported headers rather than the body centre. The pad-envelope offsets were P4 **21.627 mm**, P7 **8.980 mm**, P1 **6.350 mm**, J_BCK_5V/J_PVDD **2.840 mm**, J_BCK_3V3 **2.540 mm**, and P5/P_L2/J_VCC_PSOC **1.270 mm**. The pins themselves were always at the correct board-space pad coordinates.

`render/pipeline/scene.py` now transforms every header pad into footprint-local coordinates, computes the pad-envelope centre and spans, and places a 2.54 mm-high body there. Width/depth are the measured spans plus 2.54 mm, so dual-row bodies retain 5.08 mm depth. The existing KiCad-Y-down to Blender-Y-up rotation is unchanged, and a per-header assertion requires centre agreement within 1e-6 mm. The pin-generation loop and native PCB hash are unchanged. Derived examples: P4 45.72×5.08 mm, P7 20.32×5.08 mm, J_BCK_5V/J_PVDD 7.62×5.08 mm, P1 15.24×2.54 mm.

Close-range visual checks were made at P4/P7, P1/J_BCK, and J_PVDD/P5. Before/after crops are in `render/work/review/headers-before-*.png` and `headers-after-*.png`; the corrected bodies sit over their pads at all three locations. All 278 footprints are on the top layer, so there are no bottom-side or right-angle stand-ins to correct. Matching local vertical KiCad STEP models were found for every header size, but were not needed after the deterministic pad-envelope fix.

Other stand-ins were audited: U3/U4/U7/U8/Q2, L2, C5, and chip passives already have origin/pad-centre agreement within 0.000006 mm. J_USB1 has an intentional 1.3375 mm local pad/body-centre offset from its connector overhang and was not shifted. No pqfn/wlp/df40/vh stand-ins exist in this scene. No footprint model offsets were applied to stand-ins; embedded STEP models remain on their native import paths.

## Render verification

The final white-background product render was visually inspected after draft iterations. All footprints are accounted for (`UNMODELLED_LEFT []`), U1 sits over its pad array, MA12070P is legible, and the image has blue satin mask, metallic finishes, soft floor shadow, and no depth of field. No PCB silkscreen is visible; only the separate source-known MA12070P and IRFHM830 component markings remain. Both `render/output/kit-bt-amp-22v_2400x1800.png` and `.jpg` are exactly 2400 × 1800 RGB pixels. The portfolio JPEG is byte-identical to the final JPEG.

## Sanitization

Source-derived component properties containing historical vendor names, company URLs, and document links were cleared through Konnect. Legitimate component values and footprints were retained, including MA12070P, IRFHM830TRPbF, and package identifiers. The final case-insensitive scan covers the native schematic, symbol-library, PCB, project, and library-table files and has **no `Infineon` matches**.

Exactly two `MERUS` metadata strings remain, retained explicitly by user decision:

- `schematic/ma12070p-amplifier.kicad_sch`: title-block company `Merus Audio`.
- `kit-bt-amp-22v.kicad_pcb`: U1 footprint-library nickname `Merus:QFN50P900X900X100_HS-65N`.

Every other match from the converted native-file set was cleared. Konnect 10.0 has no operation for editing a schematic title-block `company` field or renaming a placed PCB footprint's library identifier, so these fields were not changed with unsupported text/scripts. The project does not claim complete `MERUS` sanitization.
