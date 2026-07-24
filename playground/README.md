# Playground (optional / dormant)

Scratch and experimental helpers — not used by `app.py` in normal operation
(except the shim that re-exports the root `portal_api_client`).

| Item | Purpose |
|---|---|
| `gsheet.py` | Optional Google Sheets export (was wired from `energy.py`) |
| `test_energy.py` | Manual energy-counter run without full `app.py` loop |
| `test_gsheet.py` | Manual Sheets auth / read check |
| `portal_api_client.py` | Shim → repo-root `portal_api_client.py` |
| `x40-connection.md` | LAN probe notes for local x-center x40 (no HTTP/Modbus) |
| `Input/` | Saved Heizkreis HTML/screenshots for selector tweaks |

Keep `credentials.json` / `token.json` / `secrets.py` in the **repo root** (gitignored). Run harnesses from the repo root so those paths resolve, e.g.:

```bash
python playground/test_energy.py
python portal_api_client.py once
```

To re-enable Sheets export: set `SPREADSHEET_ID` in `gsheet.py`, then in `energy.py` uncomment the `gsheet` import/call (adjust import path as needed).
