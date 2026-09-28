# OS-9 Runtime Architecture & Routing Engine IPC

> **Provenance (2026-09-28):** the listings analysed here (`dbq/*.asm`, `rpmod.asm`) are from the **Philips CARIN CC-93** (m68k, 1993) on `NAV_SW(v32).iso`, a CD-only BMW platform. The unit that reads the DB-REL 34 DVDs is the RoadRunner (MIPS), whose `rpmod`/`dbq` live in `/V_2/RR/*/app_sw/bsw2`. See [`03-firmware-provenance.md`](03-firmware-provenance.md).

This document describes the runtime execution architecture of the navigation routing engine (`rpmod`, `dbq`, etc.) on the OS-9/68k RTOS, discovered by reverse engineering the firmware.

## 1. Module Overview and Layout

The firmware binary (`NAV_SW(v32).iso`) contains exactly 1933 OS-9 modules. 
An extensive sweep proved that **all modules have been entirely stripped of their OS-9 Symbol Tables** (`SymOff = 0x00000000`). There are no debug maps, and any plaintext function names (like `CONNECT_NODE`) found in the ROM are strictly enums/field names left over in `printf` debug formatting strings, not exported symbols.

Furthermore, there are **no Subroutine modules** (`Type 0x02`) providing native OS-9 export tables for the routing engine. All dynamic resolution happens via bespoke runtime mechanics.

### Key Modules:
- `dbq`: The **Database Query** engine. This is a Program module (`Type 0x01`). It acts as the "Master/Manager" for database logic.
- `rpmod`: The **Route Planner** module. Also a Program module (`Type 0x01`). It acts as a "Slave" and heavily depends on `dbq`.
- `car_netdb`, `car_device`: Device Driver modules (`Type 0x0E`) loaded at runtime via the `F$Link` system trap by `rpmod`.

## 2. Shared Memory & Global Data Pointer (GDP)

A massive breakthrough in reversing the routing dispatch tables is understanding how memory is laid out:
- `rpmod`'s allocated Data/BSS section is only ~15KB (`0x3CB0`).
- `dbq`'s allocated Data section is ~32KB (`0x7DC1`).

In the OS-9/68k ABI, `A6` is the **Global Data Pointer (GDP)**. 
When analyzing `rpmod`, we found indirect function calls targeting extremely far negative offsets, such as `jsr -$73C6(A6)`. 
Offset `0x73C6` (29638 bytes) is **outside** of `rpmod`'s native 15KB data space, proving that `rpmod` is using `dbq`'s `A6` pointer! 
`dbq` forks or calls `rpmod`, passing its own `A6` base pointer, sharing the 32KB global data layout. 

## 3. The Dispatch Table (Branch Islands)

Because the offsets used by `rpmod` (`-$73C6`, `-$73AE`, `-$7318`, `-$7240`) fall into the BSS (uninitialized) area of `rpmod`'s DIT, they are completely zeroes natively.
However, because they share the memory layout with `dbq`, we found that **`dbq`'s Data Initialization Table (DIT) populates these exact offsets**.

The spacing between the offsets gave away the structure:
- `73C6` to `73AE` = 24 bytes (4 * 6)
- `73AE` to `7318` = 150 bytes (25 * 6)
- `7318` to `7240` = 216 bytes (36 * 6)

Every offset gap is a perfect multiple of **6 bytes**, which is the exact size of an m68k absolute jump instruction (`JMP <addr32>` / `4EF9 XX XX XX XX`). 
This proves that the runtime uses a **Branch Island Jump Table** located in the Data/BSS segment. `dbq` populates this table, resolving the external references that `rpmod` relies on.

## 4. Real Code Behind the Pointers

By mapping the Branch Island table in `dbq`'s initialized data, we extracted the actual m68k implementations of the obscure routing functions:

### 1. "Node Pointer Resolver" (`-$73C6(A6)` -> `0x00FDBE` in `dbq`)
Contrary to initial assumptions that this did complex pointer math and auto-incremented `(A0)+`, this function is actually a **Dummy Stub**:
```m68k
00fdbe: link.w     a5, #$0
00fdc2: movem.l    d0, -(a7)
00fdc6: clr.b      -$6840(a6)     ; Clear global flag
00fdca: move.l     #$1f3, d0      ; Return 0x1F3 (499)
00fdd0: unlk       a5
00fdd2: rts
```
It completely ignores the pointer in `A0`. Instead, it clears a global flag (acting as a synchronous/asynchronous semaphore for `dbq`) and returns `0x1F3`. (The caller itself was found to manually advance the pointer, not the function).

### 2. "Node Validator" (`-$73AE(A6)` -> `0x0120A6` in `dbq`)
This function doesn't compute topology natively. It invokes a system `trap #0` with parameter `$000E` (`F$Send`), which is the OS-9 syscall to send a signal to a process. 
This proves the firmware uses **asynchronous IPC (Event-Driven)** for node validation. `rpmod` essentially fires a signal to the manager process and waits or delegates the task.

### 3. "Restriction Check" (`-$7318(A6)` -> `0x00A118` in `dbq`)
A massive 116-line logic block that actively performs bitwise operations on the Arc Record (validating the reverse-engineered layout!). It extracts the nibbles at `S0.FLAGS` (`0x11` and `0x10`) to check directional restrictions, one-way streets, and turn limits.

### 4. "Special Arc Handler" (`-$7240(A6)` -> `0x011C92` in `dbq`)
A basic getter function that returns the 32-bit field at offset `+0x0C` of the struct pointer passed in `D0`.

## 5. The "Magic Number" `0x1F3`
The return value `0x1F3` (499 in decimal) appears ubiquitously across `dbq`'s resolver and restriction checks. It represents the internal status code for **"SUCCESS / AUTHORIZED / OK"** in the CARiN OS-9 routing engine. If the `Restriction Check` returns anything other than `0x1F3`, the route is blocked or restricted.
