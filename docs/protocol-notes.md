# Protocol Notes

- Scale family: Soundlogic item `19181`, batch `2140082`
- App ecosystem: `OKOK International`
- Likely protocol family: `Chipsea-BLE` / OKOK-compatible smart body scale
- Current implementation status:
  - `replay` mode is fully wired for local development
  - `live` mode decodes weight from compact advertisement packets (13-byte Chipsea format)
  - Broadcast advertisements (18-byte Chipsea format) are also supported as a fallback
  - BIA impedance extraction is wired but not yet populated by the parsers
