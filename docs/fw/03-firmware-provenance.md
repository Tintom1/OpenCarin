# Firmware Provenance — which unit reads which disc

> **Status: ✅ VERIFIED (2026-09-28).** Read this before citing firmware as evidence.
> Every firmware in this repo comes from one BMW update CD, `dataset/NAV_SW(v32).iso`
> (`/abstract`: `BMW Release_08.01`). That CD carries the software for **several hardware
> generations**, and they do not all read the same discs.

## 1. Platforms on `NAV_SW(v32).iso`

| Folder | Platform | CPU / OS | Medium it reads | Identifying strings |
|---|---|---|---|---|
| `/CC93_/0560/nav_sw_load` | **Philips CARIN CC-93** | m68k / OS-9 | CD, one `/carindb` file (`/NVCC93/nv_db` = `carindb 8`) | `(c) PHILIPS,Eindhoven CARIN CC-93 system`, `Copyright: 1993 Philips Electronics N.V.` |
| `/Mk2C/*`, `/Mk2M/*` | Mk2 | m68k / OS-9 | CD | — |
| `/Mk3/*` (`bsw_load`, `usw_load`) | Mk3 (`Carin Mk3 TSW`, 2003) | MIPS32 / OS-9000 | CD | `release: 1.27 (SPIL3A)` |
| `/V_2/RR/*` (`navboot`, `bsw2`) | **VDO Dayton RoadRunner (RR)** | MIPS32 / OS-9000 | **DVD-9** (`dvd`, `dr_atapi`, `ssp_dvd`, `fm_xcd` modules in `navboot`) | `VDO Dayton RoadRunner TSW … (RRASIC)`, `Siemens VDO Automotive RoadRunner DVD-9 is used` |
| `/PSH4/*`, `/V_2/PSH4/*` | SH-4 / Windows CE image (`Nk.fli`) | SH-4 / WinCE | not established | `SWLInstallSh4.dll` |

`sw_rel.tbl` release fields: RR `0101/BMWC01S` = `1000`, RR `0103/BMWOCN` = `2340`, Mk3 `0127` = `0630`.

## 2. Which firmware matches our discs

`dataset/NAV_DB_21708.ISO` (`/ABSTRACT`: `Medium: Master DVD9`, 2015; `/BIBLIOGR`:
`CD-ID 21708 DB-REL 34 BSW-REL 10 11`) and `High_2019_WE_SC_SL.bin` (CD-ID 21734) are
DVD-9 discs with the `/DB/DB_0` + `/DB/DB_1` split layout.

- **RR is the platform that reads them.** It is the only one with a DVD stack, and its
  `bsw2` carries the whole database/route-planner set (§3). Its release `1000` probably
  matches `BSW-REL 10` (inferred from the number, not verified).
- **CC-93 cannot read them**: CD-only hardware, a single `/carindb` file, and it predates
  block types `0x1C`–`0x1E` and the DB-REL ≥ 23 passes.
- The README line "MK4 (DVD, Hitachi SH-4)" is **not supported** by this CD: the DVD
  database reader here is MIPS (RR). The role of the SH-4/WinCE image is not established.

## 3. Database / routing modules per platform

| Module | CC-93 (m68k) — listings in `dbq/`, `rpmod/` | RR `bsw2` (MIPS) — offset in `bsw2` |
|---|---|---|
| `rpmod` (route planner) | `dbq/rpmod.asm` (~134 KB module) | `0x110cf0`, 0x8e040 B (~581 KB) |
| `dbq` (query engine) | `dbq/dbq.asm` | `0x0b7ee0` |
| `dbd` / `dbc` | `dbq/dbd.asm`, `dbq/dbc.asm` | `0x0ae168` / `0x065578` |
| `db_pub` / `pbp` (block decoders) | `dbq/pbp.asm`, excerpt `docs/fw/m68k_pbp_decoders.asm` | `db_pub` `0x0917c8` |
| `dbpa`, `db_bh_read`, `db_con` | — / partial | `0x028a78`, `0x09f938`, `0x076700` |
| `hdlbsi`, `update_carloc`, `gd_man`, `gd_bjl`, `mm`, `hdltmc`, `tpd` | partial | present |

Enumerate with `python scripts/firmware/os9_modules.py build/fw/V_2_RR_0101_BMWC01S_app_sw_bsw2`.

The MIPS `db_pub` listings in `docs/fw/mips_*.asm` were traced on **Mk3** `bsw_load`
(`scripts/firmware/mips_dis.py`, `CARIN_FW2`); the CF=1 codec they describe decodes the
DVDs, so Mk3 and RR share it.

## 4. Consequences for the docs

- Everything marked **FW** from `rpmod.asm` / `dbq.asm` / `dbd.asm` / `dbc.asm` / `pbp` is
  **CC-93** evidence: a BMW firmware of an older generation, same CARiN family. Treat it as
  a hint for DB-REL 34, not as proof. Data checks (cross-disc, OSM) decide.
- Firmware conclusions that were overturned by data came from CC-93 only: "`0x0E` is the
  routing graph", "`can_traverse` always returns 1", "`rpmod` never reads `0x00` records".
- The route planner of the unit that reads our DVDs is RR `rpmod`. First results:
  [`04-rr-rpmod-edge-record.md`](04-rr-rpmod-edge-record.md).
