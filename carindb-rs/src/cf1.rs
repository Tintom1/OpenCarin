//! CF=1 (bit-packed) block decoders. Port of `carin/parser/cf1/`:
//! core.py, decoder_00.py, decoder_0e.py, decoder_14.py.
//!
//! Python `Cf1Error` and out-of-range accesses are panics here; callers
//! (`codec::decode_block`, `probe::detect_subrel`) catch them per block.

use std::collections::HashMap;

pub const SECTOR: usize = 512;

const CHARMAP: &[u8] = b"aestr\x00 dghilno\xe0\xe1\xe2\xe3\xe4\xe5\xe7\xe8\xe9\xea\xeb\xec\xed\xee\xef\xf1\xf2\xf3\xf4\xf5\xf6\xf8\xf9\xfa\xfb\xfc\xfd\xac";

// RECORD_SIZE_TABLE indices (constants.py)
const T_DESC_BASE: u16 = 0x05;
const T_REC_S6: u16 = 0x06;
const T_REC_S4: u16 = 0x08;
const T_TAIL_S4: u16 = 0x09;
const T_PROLOG: u16 = 0x0B;
const T_REC_S7: u16 = 0x0C;
const T_REC_S9: u16 = 0x0F;
const T_REC_S5: u16 = 0x10;
const T_REC_S3: u16 = 0x12;
const T_REC_S11: u16 = 0x13;
const T_REC_S10: u16 = 0x14;
const T_REC_S12: u16 = 0x15;
const T_REC_S0: u16 = 0x40;
const T_REC_S13: u16 = 0x4C;
const T_REC_S14: u16 = 0x59;
// 0x0E
const T_PROLOG_0E: u16 = 0x2B;
const T_REC_S0_0E: u16 = 0x2D;
const T_REC_S1_0E: u16 = 0x41;
const T_REC_S2_0E: u16 = 0x42;
// 0x14-0x16, 0x1C-0x1E
const T_PROLOG_141516: u16 = 0x3D;
const T_REC_S1_141516: u16 = 0x3A;
const T_REC_S0_141516: u16 = 0x3B;
const T_REC_S2_141516: u16 = 0x3C;
const T_S3_DISP_141516: u16 = 0x3F;
const T_REC_E4_141516: u16 = 0x15;
const T_REC_E5_141516: u16 = 0x59;

/// pbp+0x4a68: bits needed for 0..n-1, 16-bit arithmetic (0 wraps to 16, as in Python).
pub fn bits_needed(n: usize) -> usize {
    let v = (n & 0xFFFF) as u16;
    if v == 1 { return 1; }
    let mut v = v.wrapping_sub(1);
    let mut out = 0;
    while v != 0 {
        v >>= 1;
        out += 1;
    }
    out
}

#[derive(Clone, Copy)]
pub struct Entry {
    pub off: usize,
    pub count: usize,
}

struct Ctx<'a> {
    table: &'a HashMap<u16, u16>,
    src: &'a [u8],
    dst: Vec<u8>,
    cursor: usize,
    ptrbits: usize,
    widths: [u8; 2],
    bitpos: usize,
    pb: HashMap<&'static str, usize>,
    dbrel: u16,
    subrel: u16,
    cache_s7: usize,
    cache_s2: usize,
    m_hi: u8,
    m_lo: u8,
}

impl<'a> Ctx<'a> {
    fn new(table: &'a HashMap<u16, u16>, src: &'a [u8], total: usize, dbrel: u16, subrel: u16) -> Self {
        Self {
            table, src, dst: vec![0; total], cursor: 0, ptrbits: bits_needed(total), widths: [0, 0],
            bitpos: 0, pb: HashMap::new(), dbrel, subrel, cache_s7: 1, cache_s2: 1, m_hi: 0, m_lo: 0,
        }
    }

    fn t(&self, idx: u16) -> usize {
        match self.table.get(&idx) {
            Some(v) => *v as usize,
            None => panic!("RECORD_SIZE_TABLE lacks entry {idx:#x}"),
        }
    }

    fn copy_raw(&mut self, dst_off: isize, n: usize) -> Vec<u8> {
        let end = self.cursor + n;
        if end > self.src.len() {
            panic!("truncated stream: need {n} bytes at {}", self.cursor);
        }
        let chunk = self.src[self.cursor..end].to_vec();
        if dst_off >= 0 {
            self.dst[dst_off as usize..dst_off as usize + n].copy_from_slice(&chunk);
        }
        self.cursor = end;
        chunk
    }

    fn entry(&self, idx: usize) -> Entry {
        let base = self.t(T_DESC_BASE) + 4 * idx;
        Entry {
            off: u16::from_be_bytes([self.dst[base], self.dst[base + 1]]) as usize,
            count: u16::from_be_bytes([self.dst[base + 2], self.dst[base + 3]]) as usize,
        }
    }

    fn copy_section(&mut self, idx: usize, recsize: usize, plus1: bool) {
        let e = self.entry(idx);
        let n = e.count * recsize + if plus1 { recsize } else { 0 };
        self.copy_raw(e.off as isize, n);
    }

    fn bits_init(&mut self) { self.bitpos = self.cursor * 8; }

    /// MSB-first `BFEXTU`; reads past the end yield zero bits.
    fn g(&mut self, width: usize) -> u32 {
        if width == 0 { return 0; }
        let mut out = 0u64;
        let mut left = width;
        while left > 0 {
            let idx = self.bitpos >> 3;
            let avail = 8 - (self.bitpos & 7);
            let take = left.min(avail);
            let byte = self.src.get(idx).copied().unwrap_or(0) as u64;
            out = (out << take) | ((byte >> (avail - take)) & ((1 << take) - 1));
            self.bitpos += take;
            left -= take;
        }
        out as u32
    }

    fn w(&mut self, off: usize, val: u32) { self.dst[off..off + 2].copy_from_slice(&(val as u16).to_be_bytes()); }
    fn rw(&self, off: usize) -> u32 { u16::from_be_bytes([self.dst[off], self.dst[off + 1]]) as u32 }
    fn b(&mut self, off: usize, val: u32) { self.dst[off] = val as u8; }
    fn l(&mut self, off: usize, val: u32) { self.dst[off..off + 4].copy_from_slice(&val.to_be_bytes()); }
}

fn walk<F: FnMut(&mut Ctx, usize, isize, bool)>(ctx: &mut Ctx, idx: usize, recsize: usize, mut cb: F) {
    let e = ctx.entry(idx);
    let end = e.off + e.count * recsize;
    let (mut cur, mut prev) = (e.off, -1isize);
    while cur < end {
        cb(ctx, cur, prev, cur == e.off);
        prev = cur as isize;
        cur += recsize;
    }
}

// ------------------------------------------------------------ type 0x00

fn delta(ctx: &mut Ctx, prev_val: u32) -> u32 {
    let width = ctx.widths[1] as usize;
    if ctx.g(1) == 1 {
        if ctx.g(1) == 1 { return ctx.g(16); }
        return prev_val.wrapping_sub(ctx.g(width)) & 0xFFFF;
    }
    prev_val.wrapping_add(ctx.g(width)) & 0xFFFF
}

fn dec_a14(ctx: &mut Ctx, idx: usize) {
    let pb = ctx.ptrbits;
    let rec = ctx.t(T_REC_S0);
    walk(ctx, idx, rec, |c, cur, prev, _| {
        if c.g(1) == 1 {
            let v2 = c.g(pb);
            let v4 = c.g(pb - 1) << 1;
            if idx != 0 {
                c.w(cur + 2, v2);
                c.w(cur + 4, v4);
            }
        } else if idx != 0 && prev >= 0 {
            c.w(cur + 2, c.rw(prev as usize + 2));
            c.w(cur + 4, c.rw(prev as usize + 4));
        }
        let v0 = c.g(pb);
        c.w(cur, v0);
    });
}

fn dec_a15_s0(ctx: &mut Ctx) {
    let rec = ctx.t(T_REC_S0);
    walk(ctx, 0, rec, |c, cur, prev, _| {
        if c.g(1) == 1 {
            let v = c.g(16);
            c.w(cur + 2, v);
        } else if prev >= 0 {
            c.w(cur + 2, c.rw(prev as usize + 2));
        }
    });
}

fn dec_a17_s0(ctx: &mut Ctx) {
    let rec = ctx.t(T_REC_S0);
    walk(ctx, 0, rec, |c, cur, _, _| {
        let v = c.g(c.ptrbits - 1) << 1;
        c.w(cur + 4, v);
    });
}

fn dec_a17_s1(ctx: &mut Ctx) {
    let pb = ctx.ptrbits;
    let rec = ctx.t(T_REC_S0);
    walk(ctx, 1, rec, |c, cur, _, _| {
        let v6 = c.g(pb - 1) << 1;
        c.w(cur + 6, v6);
        let v8 = c.g(pb - 1) << 1;
        c.w(cur + 8, v8);
    });
}

fn dec_a17_s2(ctx: &mut Ctx) {
    let pb = ctx.ptrbits;
    let rec = ctx.t(T_REC_S0);
    let (mut step, mut acc) = ([0u32; 2], [0u32; 2]);
    walk(ctx, 2, rec, |c, cur, _, _| {
        for (k, off) in [6usize, 8].into_iter().enumerate() {
            if c.g(1) == 1 {
                step[k] = (c.g(pb - 1) << 1) & 0xFFFF;
            }
            acc[k] = (step[k] + acc[k]) & 0xFFFF;
            c.w(cur + off, acc[k]);
        }
    });
}

fn pbits(ctx: &Ctx, key: &str) -> usize {
    *ctx.pb.get(key).unwrap_or_else(|| panic!("pb[{key}] not set"))
}

/// Section 4 record group written by the 0x14 pass (S10/S12/S11 pointers).
fn ptr_group(ctx: &mut Ctx, at: usize, e10: Entry, e11: Entry, e12: Entry, tail: usize) {
    let (b10, b11, b12) = (pbits(ctx, "s10"), pbits(ctx, "s11"), pbits(ctx, "s12"));
    let v = e10.off + ctx.g(b10) as usize * ctx.t(T_REC_S10);
    ctx.w(at + 0x12, v as u32);
    let v = e12.off + ctx.g(b12) as usize * ctx.t(T_REC_S12);
    ctx.w(at + 0x14, v as u32);
    let v = e11.off + ctx.g(b11) as usize * ctx.t(T_REC_S11);
    ctx.w(at + tail + 4, v as u32);
}

fn s13_ptr(ctx: &mut Ctx, at: usize, prv: isize, e13: Entry) {
    if ctx.g(1) == 1 {
        let bits = pbits(ctx, "s13");
        let v = e13.off + ctx.g(bits) as usize * ctx.t(T_REC_S13);
        ctx.w(at + 0x16, v as u32);
    } else if prv >= 0 {
        ctx.w(at + 0x16, ctx.rw(prv as usize + 0x16));
    }
}

fn dec_b(ctx: &mut Ctx, kind: u8) {
    let e4 = ctx.entry(4);
    let (e2, e7, e10, e11, e12, e13) = (ctx.entry(2), ctx.entry(7), ctx.entry(10), ctx.entry(11), ctx.entry(12), ctx.entry(13));
    let (rec, tail) = (ctx.t(T_REC_S4), ctx.t(T_TAIL_S4));
    let pb = ctx.ptrbits;
    let (start, end) = (e4.off, e4.off + e4.count * rec);
    let (mut cur, mut prev) = (start, -1isize);

    while cur < end {
        match kind {
            0x14 => {
                if cur != start {
                    ctx.dst.copy_within(prev as usize..prev as usize + rec, cur);
                }
                if ctx.g(1) == 1 { ptr_group(ctx, cur, e10, e11, e12, tail); }
                if ctx.g(1) == 1 {
                    let v = ctx.g(8); ctx.b(cur + 0x0A, v);
                    let v = ctx.g(8); ctx.b(cur + 0x0B, v);
                    let v = ctx.g(8); ctx.b(cur + 0x10, v);
                    let v = ctx.g(8); ctx.b(cur + 0x11, v);
                    let v = ctx.g(16); ctx.w(cur + tail + 2, v);
                }
                let v = ctx.g(pb - 1) << 1; ctx.w(cur, v);
                let v = ctx.g(pb - 1) << 1; ctx.w(cur + 2, v);
                if ctx.g(1) == 1 {
                    let bits = pbits(ctx, "s7");
                    ctx.cache_s7 = e7.off + ctx.g(bits) as usize * ctx.t(T_REC_S7);
                }
                ctx.w(cur + 4, ctx.cache_s7 as u32);
                for off in [0x06usize, 0x08] {
                    let bits = pbits(ctx, "s4");
                    let t = ctx.g(bits) as usize;
                    ctx.w(cur + off, if t == e4.count { 0 } else { (e4.off + t * rec) as u32 });
                }
                let width = if ctx.g(1) == 1 { 16 } else { ctx.widths[0] as usize };
                let v = ctx.g(width); ctx.w(cur + 0x0C, v);
                let v = ctx.g(8); ctx.b(cur + 0x0E, v);
                let v = ctx.g(8); ctx.b(cur + 0x0F, v);
                if ctx.g(1) == 1 {
                    let bits = pbits(ctx, "s2");
                    ctx.cache_s2 = e2.off + ctx.g(bits) as usize * ctx.t(T_REC_S0);
                }
                ctx.w(cur + tail, ctx.cache_s2 as u32);
            }
            0x15 => s13_ptr(ctx, cur, prev, e13),
            0x1B => {
                // RR sub_005594 +0x5b5c: two bytes, or both copied from the previous record
                if ctx.g(1) == 1 {
                    let v = ctx.g(8); ctx.b(cur + 0x18, v);
                    let v = ctx.g(8); ctx.b(cur + 0x19, v);
                } else if prev >= 0 {
                    ctx.dst[cur + 0x18] = ctx.dst[prev as usize + 0x18];
                    ctx.dst[cur + 0x19] = ctx.dst[prev as usize + 0x19];
                }
            }
            _ => {}
        }
        prev = cur as isize;
        cur += rec;
    }

    if kind == 0x15 { s13_ptr(ctx, cur, prev, e13); } // sentinel record
    if kind != 0x14 { return; }
    // trailing sentinel record (section has count+1 records)
    if ctx.g(1) == 1 {
        ptr_group(ctx, cur, e10, e11, e12, tail);
    } else if prev >= 0 {
        let p = prev as usize;
        ctx.w(cur + 0x12, ctx.rw(p + 0x12));
        ctx.w(cur + 0x14, ctx.rw(p + 0x14));
        ctx.w(cur + tail + 4, ctx.rw(p + tail + 4));
    }
    if ctx.g(1) == 1 {
        let bits = pbits(ctx, "s7");
        ctx.cache_s7 = e7.off + ctx.g(bits) as usize * ctx.t(T_REC_S7);
    }
    ctx.w(cur + 4, ctx.cache_s7 as u32);
}

fn dec_xy(ctx: &mut Ctx, idx: usize, recsize: usize, extra: impl Fn(&mut Ctx, usize)) {
    let e4 = ctx.entry(4);
    let rec_s4 = ctx.t(T_REC_S4);
    let s4_bits = pbits(ctx, "s4");
    walk(ctx, idx, recsize, |c, cur, prev, first| {
        if c.g(1) == 1 {
            let v = c.g(8); c.b(cur + 6, v);
            let v = c.g(3); c.b(cur + 7, v);
        } else if prev >= 0 {
            c.dst[cur + 6] = c.dst[prev as usize + 6];
            c.dst[cur + 7] = c.dst[prev as usize + 7];
        }
        if first {
            let v = c.g(16); c.w(cur, v);
            let v = c.g(16); c.w(cur + 2, v);
        } else {
            let p = prev as usize;
            let v = delta(c, c.rw(p)); c.w(cur, v);
            let v = delta(c, c.rw(p + 2)); c.w(cur + 2, v);
        }
        let v = e4.off + c.g(s4_bits) as usize * rec_s4;
        c.w(cur + 4, v as u32);
        extra(c, cur);
    });
}

fn dec_c(ctx: &mut Ctx) {
    let rec = ctx.t(T_REC_S5);
    dec_xy(ctx, 5, rec, |_, _| {});
}

fn dec_d(ctx: &mut Ctx) {
    let rec = ctx.t(T_REC_S6);
    let off5 = ctx.t(T_REC_S5);
    dec_xy(ctx, 6, rec, |c, cur| {
        let v = c.g(32); c.l(cur + off5, v);
        // db_pub+0x4604: width depends on the format sub-revision
        let width = if c.subrel >= 9 { 16 } else { 14 };
        let v = c.g(width); c.w(cur + off5 + 4, v);
    });
}

fn dec_e(ctx: &mut Ctx) {
    let rec = ctx.t(T_REC_S7);
    walk(ctx, 7, rec, |c, cur, prev, first| {
        if first {
            let v = c.g(16); c.w(cur, v);
            let v = c.g(16); c.w(cur + 2, v);
        } else {
            let p = prev as usize;
            let v = delta(c, c.rw(p)); c.w(cur, v);
            let v = delta(c, c.rw(p + 2)); c.w(cur + 2, v);
        }
        let v = c.g(3); c.b(cur + 4, v);
    });
}

fn dec_f(ctx: &mut Ctx) {
    let pb = ctx.ptrbits;
    let rec = ctx.t(T_REC_S11);
    walk(ctx, 11, rec, |c, cur, _, _| {
        let v = c.g(pb); c.w(cur, v);
        let v = c.g(pb); c.w(cur + 2, v);
        let v = c.g(1); c.w(cur + 4, v);
    });
}

fn dec_s13(ctx: &mut Ctx) {
    let pb = ctx.ptrbits;
    let rec = ctx.t(T_REC_S13);
    walk(ctx, 13, rec, |c, cur, _, _| {
        let v = c.g(32); c.l(cur, v);
        let v = c.g(pb); c.w(cur + 4, v);
        let v = c.g(8); c.b(cur + 6, v);
        let v = c.g(8); c.b(cur + 7, v);
    });
}

fn dec_s14(ctx: &mut Ctx) {
    let pb = ctx.ptrbits;
    let rec = ctx.t(T_REC_S14);
    walk(ctx, 14, rec, |c, cur, prev, _| {
        if c.g(1) == 1 { let v = c.g(pb); c.w(cur, v); }
        else if prev >= 0 { c.w(cur, c.rw(prev as usize)); }
        if c.g(1) == 1 { let v = c.g(8); c.b(cur + 2, v); }
        else if prev >= 0 { c.dst[cur + 2] = c.dst[prev as usize + 2]; }
        if c.g(1) == 1 { let v = c.g(5); c.b(cur + 3, v); }
        else if prev >= 0 { c.dst[cur + 3] = c.dst[prev as usize + 3]; }
    });
}

/// First byte past numbered record sections 0..13 (decoder_00 `_sections_end`).
fn sections_end_00(ctx: &Ctx) -> usize {
    const SECT_REC: [(usize, u16); 13] = [
        (0, T_REC_S0), (1, T_REC_S0), (2, T_REC_S0), (3, T_REC_S3), (4, T_REC_S4), (5, T_REC_S5),
        (6, T_REC_S6), (7, T_REC_S7), (9, T_REC_S9), (10, T_REC_S10), (11, T_REC_S11),
        (12, T_REC_S12), (13, T_REC_S13),
    ];
    let mut hi = 0;
    for (idx, key) in SECT_REC {
        let e = ctx.entry(idx);
        if e.count == 0 { continue; }
        if let Some(&rec) = ctx.table.get(&key) {
            hi = hi.max(e.off + e.count * rec as usize);
        }
    }
    hi
}

/// Name blob: prefix code + per-block dictionary. `floor` = first byte past the
/// record sections; writes below it are suppressed.
fn dec_text(ctx: &mut Ctx, floor: Option<usize>) {
    let pb = ctx.ptrbits;
    let start = ctx.g(pb) as usize;
    let end = ctx.g(pb) as usize;
    if start == 0 && end == 0 { return; }
    let mut words: Vec<Vec<u8>> = Vec::with_capacity(6);
    for _ in 0..6 {
        let n = ctx.g(5) as usize;
        words.push((0..n).map(|_| ctx.g(7) as u8).collect());
    }
    let floor = floor.unwrap_or_else(|| sections_end_00(ctx));
    let ok = start <= end && end < ctx.dst.len() && start >= floor;
    let mut p = start;
    while p <= end && p < ctx.dst.len() {
        let code = ctx.g(2);
        let v = match code {
            0 => CHARMAP[ctx.g(1) as usize],
            1 => CHARMAP[2 + ctx.g(2) as usize],
            2 => CHARMAP[6 + ctx.g(3) as usize],
            _ => {
                let v = ctx.g(7) as usize;
                if v <= 0x26 {
                    if v > 0x1B {
                        // Python: words[v - 0x21] with negative wrap-around for v in 0x1C..=0x20
                        let w = &words[(v as isize - 0x21).rem_euclid(6) as usize];
                        if ok {
                            let n = w.len().min(ctx.dst.len() - p);
                            ctx.dst[p..p + n].copy_from_slice(&w[..n]);
                        }
                        p += w.len();
                        continue;
                    }
                    CHARMAP[14 + v]
                } else {
                    v as u8
                }
            }
        };
        if ok { ctx.dst[p] = v; }
        p += 1;
    }
}

/// db_pub+0x3d04 — BLOCK_TYPE 0x00.
fn decode_00(ctx: &mut Ctx) {
    let prolog = ctx.t(T_PROLOG);
    ctx.copy_raw(0, prolog);
    for (key, idx, plus) in [("s2", 2, 0), ("s4", 4, 1), ("s7", 7, 1), ("s10", 10, 1), ("s11", 11, 1), ("s12", 12, 1)] {
        let bits = bits_needed(ctx.entry(idx).count + plus);
        ctx.pb.insert(key, bits);
    }
    let w = ctx.copy_raw(-1, 2);
    ctx.widths = [w[0], w[1]];
    let r = ctx.t(T_REC_S3); ctx.copy_section(3, r, true);
    let r = ctx.t(T_REC_S9); ctx.copy_section(9, r, false);
    let r = ctx.t(T_REC_S10); ctx.copy_section(10, r, false);
    if ctx.entry(12).count > 0 {
        let r = ctx.t(T_REC_S12); ctx.copy_section(12, r, false);
    }
    ctx.bits_init();

    // pass 0x14 (DB-REL 20)
    for idx in 0..=2 { dec_a14(ctx, idx); }
    dec_b(ctx, 0x14);
    dec_c(ctx);
    dec_d(ctx);
    dec_e(ctx);
    if ctx.entry(11).count > 0 { dec_f(ctx); }
    dec_text(ctx, None);

    if ctx.dbrel < 0x15 { return; }
    // pass 0x15 (DB-REL 21)
    let bits = bits_needed(ctx.entry(13).count + 1);
    ctx.pb.insert("s13", bits);
    dec_a15_s0(ctx);
    dec_b(ctx, 0x15);
    dec_s13(ctx);

    if ctx.dbrel < 0x17 { return; }
    // pass 0x17 (DB-REL 23)
    dec_s14(ctx);
    dec_a17_s2(ctx);
    dec_a17_s1(ctx);
    dec_a17_s0(ctx);
    if ctx.g(1) == 1 { dec_text(ctx, None); }
    if ctx.g(1) == 1 { dec_text(ctx, None); }

    if ctx.dbrel < 0x1B { return; }
    // pass 0x1B (DB-REL 27), RR sub_005e6c +0x6e70
    dec_b(ctx, 0x1B);
}

// ------------------------------------------------------------ type 0x0E

fn s2_offset_bits(subrel: u16) -> usize { if subrel >= 9 { 15 } else { 13 } }

fn dec_0e_s0(ctx: &mut Ctx, e1: Entry) {
    let pb = ctx.ptrbits;
    let pb_s1 = bits_needed(e1.count);
    let s1_rec = ctx.t(T_REC_S1_0E);
    let rec = ctx.t(T_REC_S0_0E);
    walk(ctx, 0, rec, |c, cur, prev, _| {
        let v = c.g(pb); c.w(cur, v); // A
        let lo = c.g(2);
        let hi = c.g(1) << 4;
        c.b(cur + 2, lo | hi); // FLAGS
        if c.g(1) == 1 {
            let v = c.g(3); c.b(cur + 3, v);
            let v = c.g(pb); c.w(cur + 4, v);
        } else if prev >= 0 {
            let p = prev as usize;
            c.dst[cur + 3] = c.dst[p + 3];
            c.w(cur + 4, c.rw(p + 4));
        }
        let d_idx = c.g(pb_s1) as usize;
        c.w(cur + 6, (e1.off + d_idx * s1_rec) as u32);
    });
}

fn dec_0e_s1(ctx: &mut Ctx, e2: Entry) {
    let pb_s2 = bits_needed(e2.count);
    let s1_rec = ctx.t(T_REC_S1_0E);
    let s2_rec = ctx.t(T_REC_S2_0E);
    walk(ctx, 1, s1_rec, |c, cur, _, _| {
        let idx = c.g(pb_s2) as usize;
        c.w(cur, (e2.off + idx * s2_rec) as u32);
        let cnt = if c.g(1) == 1 { c.g(pb_s2) + 2 } else { 1 };
        c.b(cur + 2, cnt);
        let v = c.g(1); c.b(cur + 3, v);
    });
}

fn dec_0e_s2(ctx: &mut Ctx, count_n: usize, raw12: &[u8], m_hi: usize, m_lo: usize) {
    let e2 = ctx.entry(2);
    let idx_bits = bits_needed(count_n);
    let s2_rec = ctx.t(T_REC_S2_0E);
    for i in 0..e2.count {
        let base = e2.off + i * s2_rec;
        let idx_n = ctx.g(idx_bits) as usize;
        if idx_n < count_n {
            let anc = idx_n * 12;
            ctx.dst[base..base + 8].copy_from_slice(&raw12[anc..anc + 8]);
            ctx.dst[base + 16..base + 20].copy_from_slice(&raw12[anc + 8..anc + 12]);
        }
        let mut raw_d = [0x7FFFu32; 4];
        if ctx.g(1) == 1 {
            for d in raw_d.iter_mut() {
                let w = if ctx.g(1) == 1 { 16 } else { m_hi };
                *d = ctx.g(w);
            }
        }
        for (k, d) in raw_d.iter().enumerate() { ctx.w(base + 8 + 2 * k, *d); }
        let v1 = ctx.g(s2_offset_bits(ctx.subrel)) << 1;
        let v2 = ctx.g(m_lo);
        ctx.w(base + 20, v1);
        ctx.w(base + 22, v2);
    }
}

fn decode_0e(ctx: &mut Ctx) {
    let prolog = ctx.t(T_PROLOG_0E);
    ctx.copy_raw(0, prolog);
    let c = ctx.copy_raw(-1, 2);
    let count_n = u16::from_be_bytes([c[0], c[1]]) as usize;
    let raw12 = ctx.copy_raw(-1, count_n * 12);
    let mm = ctx.copy_raw(-1, 2);
    let (m_hi, m_lo) = (mm[0], mm[1]);
    ctx.m_hi = m_hi;
    ctx.m_lo = m_lo;
    let (e1, e2) = (ctx.entry(1), ctx.entry(2));
    ctx.bits_init();
    dec_0e_s0(ctx, e1);
    dec_0e_s1(ctx, e2);
    dec_0e_s2(ctx, count_n, &raw12, m_hi as usize, m_lo as usize);
    let s2_rec = ctx.t(T_REC_S2_0E);
    dec_text(ctx, Some(e2.off + e2.count * s2_rec));
}

// ------------------------------------------------- types 0x14-0x16, 0x1C-0x1E

const KIND_S0: u8 = 0x80;
const KIND_S1: u8 = 0x7F;
const KIND_S2: u8 = 0x81;
const KIND_S3_ABS: u8 = 0xAE;
const KIND_S3_DELTA: u8 = 0xAC;
const KIND_E4: u8 = 0x17;
const KIND_E5: u8 = 0x10;
const PASS_BASE: u8 = 0x0E;
const PASS_20: u8 = 0x14;
const PASS_23: u8 = 0x17;

struct State {
    raw4: [u8; 4],
    pb_s3: usize,
    s3_rec: usize,
    w5: [u8; 5],
}

fn s3_record_size(ctx: &Ctx) -> usize {
    let off = ctx.t(T_DESC_BASE) + ctx.t(T_S3_DISP_141516) + 0x10;
    if u16::from_be_bytes([ctx.dst[off], ctx.dst[off + 1]]) == 0 { 8 } else { 4 }
}

/// `getbits(1) ? getbits(16) : getbits(width)`
fn flag_or(ctx: &mut Ctx, width: usize) -> u32 {
    if ctx.g(1) == 1 { ctx.g(16) } else { ctx.g(width) }
}

/// sub_004228 — one pass over section `idx`.
fn section_14(ctx: &mut Ctx, idx: usize, rec: usize, kind: u8, pass: u8, st: &State) {
    let e = ctx.entry(idx);
    if e.count == 0 { return; }
    let mut last = (e.off + (e.count - 1) * rec) & 0xFFFF;
    if matches!(kind, KIND_S0 | KIND_S1 | KIND_S2) { last = (last + rec) & 0xFFFF; }
    let pb = ctx.ptrbits;
    let e3_off = ctx.entry(3).off;
    let (mut prev_s3, mut prev_e5): (Option<usize>, Option<usize>) = (None, None);
    let mut cur = e.off;
    while cur <= last {
        match kind {
            KIND_S3_ABS => {
                let v = ctx.g(32); ctx.l(cur, v);
                let v = ctx.g(32); ctx.l(cur + 4, v);
            }
            KIND_S3_DELTA => {
                if cur == e.off {
                    let v = ctx.g(16); ctx.w(cur, v);
                    let v = ctx.g(16); ctx.w(cur + 2, v);
                } else {
                    for f in [0usize, 2] {
                        let prev = ctx.rw(prev_s3.unwrap() + f) as i64;
                        let w = st.raw4[2] as usize;
                        let v = if ctx.g(1) == 1 {
                            if ctx.g(1) == 1 { ctx.g(16) as i64 } else { prev - ctx.g(w) as i64 }
                        } else {
                            prev + ctx.g(w) as i64
                        };
                        ctx.w(cur + f, v as u32);
                    }
                }
                prev_s3 = Some(cur);
            }
            KIND_S0 => {
                let v = ctx.g(7); ctx.b(cur, v);
                let v = ctx.g(1); ctx.b(cur + 1, v);
                let v = ctx.g(pb - 1) << 1; ctx.w(cur + 2, v);
            }
            KIND_S1 => match pass {
                PASS_BASE => {
                    let v = ctx.g(pb); ctx.w(cur, v);
                    let v = e3_off + ctx.g(st.pb_s3) as usize * st.s3_rec; ctx.w(cur + 2, v as u32);
                    let w = if ctx.g(1) == 1 { 32 } else { st.raw4[1] as usize };
                    let v = ctx.g(w); ctx.l(cur + 4, v);
                    let v = ctx.g(32); ctx.l(cur + 8, v);
                    let v = ctx.g(32); ctx.l(cur + 12, v);
                }
                PASS_20 => {
                    let v = ctx.g(pb - 1) << 1; ctx.w(cur + 0x10, v);
                    flag_or(ctx, st.w5[0] as usize); // read, not stored
                }
                PASS_23 => {
                    let v = ctx.g(pb - 1) << 1; ctx.w(cur + 0x12, v);
                }
                _ => {}
            },
            KIND_S2 => match pass {
                PASS_BASE => {
                    let v = ctx.g(pb); ctx.w(cur, v);
                    let v = e3_off + ctx.g(st.pb_s3) as usize * st.s3_rec; ctx.w(cur + 2, v as u32);
                    let w = if ctx.g(1) == 1 { 32 } else { st.raw4[0] as usize };
                    let v = ctx.g(w); ctx.l(cur + 4, v);
                }
                PASS_20 => {
                    let v = ctx.g(pb - 1) << 1; ctx.w(cur + 8, v);
                    let v = flag_or(ctx, st.w5[1] as usize); ctx.w(cur + 0x0A, v);
                }
                PASS_23 => {
                    let v = ctx.g(pb - 1) << 1; ctx.w(cur + 0x0C, v);
                }
                _ => {}
            },
            KIND_E4 if pass == PASS_20 => {
                for f in 0..3usize {
                    let v = flag_or(ctx, st.w5[2 + f] as usize);
                    ctx.w(cur + 2 * f, v);
                }
            }
            KIND_E5 if pass == PASS_23 => {
                for (off, width, size) in [(0usize, pb, 2usize), (2, 8, 1), (3, 5, 1)] {
                    let v = if ctx.g(1) == 1 {
                        ctx.g(width)
                    } else if let Some(p) = prev_e5 {
                        if size == 2 { ctx.rw(p + off) } else { ctx.dst[p + off] as u32 }
                    } else {
                        panic!("e5 record at {cur}: first record inherits +{off}");
                    };
                    if size == 2 { ctx.w(cur + off, v) } else { ctx.b(cur + off, v) }
                }
                prev_e5 = Some(cur);
            }
            _ => {}
        }
        cur = (cur + rec) & 0xFFFF;
    }
}

/// S2 +0x0e: last pass, derived from data (not in the RR firmware).
fn s2_tail(ctx: &mut Ctx) {
    let e = ctx.entry(2);
    if e.count == 0 { return; }
    let rec = ctx.t(T_REC_S2_141516);
    let mut prev: Option<u32> = None;
    for k in 0..=e.count {
        let cur = e.off + k * rec;
        if ctx.g(1) == 1 {
            prev = Some(ctx.g(16));
        } else if prev.is_none() {
            panic!("S2 record at {cur}: first record inherits +0x0e");
        }
        ctx.w(cur + 0x0E, prev.unwrap());
    }
}

fn sections_end_14(ctx: &Ctx) -> usize {
    let mut recs = vec![ctx.t(T_REC_S0_141516), ctx.t(T_REC_S1_141516), ctx.t(T_REC_S2_141516),
                        s3_record_size(ctx), ctx.t(T_REC_E4_141516)];
    if ctx.dbrel >= 0x17 { recs.push(ctx.t(T_REC_E5_141516)); }
    let mut hi = ctx.t(T_PROLOG_141516);
    for (i, rec) in recs.into_iter().enumerate() {
        let e = ctx.entry(i);
        if e.count > 0 {
            hi = hi.max(e.off + (e.count + if i < 3 { 1 } else { 0 }) * rec);
        }
    }
    hi
}

fn decode_14_16(ctx: &mut Ctx) {
    let prolog = ctx.t(T_PROLOG_141516);
    ctx.copy_raw(0, prolog);
    let d = ctx.t(T_DESC_BASE) + 14;
    let e3_count = u16::from_be_bytes([ctx.dst[d], ctx.dst[d + 1]]) as usize;
    let r4 = ctx.copy_raw(-1, 4);
    let mut st = State { raw4: [r4[0], r4[1], r4[2], r4[3]], pb_s3: bits_needed(e3_count + 1), s3_rec: s3_record_size(ctx), w5: [0; 5] };
    ctx.bits_init();
    let floor = sections_end_14(ctx);

    let (r0, r1, r2) = (ctx.t(T_REC_S0_141516), ctx.t(T_REC_S1_141516), ctx.t(T_REC_S2_141516));
    section_14(ctx, 0, r0, KIND_S0, PASS_BASE, &st);
    section_14(ctx, 1, r1, KIND_S1, PASS_BASE, &st);
    section_14(ctx, 2, r2, KIND_S2, PASS_BASE, &st);
    let s3_kind = if st.s3_rec == 8 { KIND_S3_ABS } else { KIND_S3_DELTA };
    section_14(ctx, 3, st.s3_rec, s3_kind, PASS_BASE, &st);
    dec_text(ctx, Some(floor));

    if ctx.dbrel < 0x14 { return; }
    for i in 0..5 { st.w5[i] = ctx.g(8) as u8; }
    let r_e4 = ctx.t(T_REC_E4_141516);
    section_14(ctx, 4, r_e4, KIND_E4, PASS_20, &st);
    section_14(ctx, 1, r1, KIND_S1, PASS_20, &st);
    section_14(ctx, 2, r2, KIND_S2, PASS_20, &st);

    if ctx.dbrel < 0x17 { return; }
    let r_e5 = ctx.t(T_REC_E5_141516);
    section_14(ctx, 5, r_e5, KIND_E5, PASS_23, &st);
    section_14(ctx, 1, r1, KIND_S1, PASS_23, &st);
    section_14(ctx, 2, r2, KIND_S2, PASS_23, &st);
    if ctx.g(1) == 1 { dec_text(ctx, Some(floor)); }
    if ctx.g(1) == 1 { dec_text(ctx, Some(floor)); }
    if ctx.dbrel > 0x17 { s2_tail(ctx); }
}

// ------------------------------------------------------------ dispatch

/// Block types with a CF=1 decoder.
pub fn supports(btype: u16) -> bool {
    matches!(btype, 0x00 | 0x0E | 0x14 | 0x15 | 0x16 | 0x1C | 0x1D | 0x1E)
}

/// Decode a CF=1 block (`raw` = on-disc bytes, header included) — `cf1.decode_block`.
/// Panics on malformed input or unsupported type; callers catch.
pub fn decode_block(raw: &[u8], table: &HashMap<u16, u16>, dbrel: u16, subrel: u16) -> Vec<u8> {
    let btype = u16::from_be_bytes([raw[4], raw[5]]);
    assert!(raw[6] & 1 == 1, "block not CF=1 (CF={})", raw[6]);
    let total = raw[7] as usize * SECTOR;
    let mut ctx = Ctx::new(table, raw, total, dbrel, subrel);
    match btype {
        0x00 => decode_00(&mut ctx),
        0x0E => decode_0e(&mut ctx),
        0x14 | 0x15 | 0x16 | 0x1C | 0x1D | 0x1E => decode_14_16(&mut ctx),
        _ => panic!("BLOCK_TYPE {btype:#04x}: no CF=1 decoder"),
    }
    // bytes 6/7 hold M_lo/M_hi (0x0E) or the widths (0x00), else zero
    let (b6, b7) = if ctx.m_hi != 0 { (ctx.m_lo, ctx.m_hi) } else { (ctx.widths[0], ctx.widths[1]) };
    ctx.dst[6] = b6;
    ctx.dst[7] = b7;
    ctx.dst
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bits_needed() {
        assert_eq!(bits_needed(0), 16); // 16-bit wrap, matches core.py
        assert_eq!(bits_needed(1), 1);
        assert_eq!(bits_needed(2), 1);
        assert_eq!(bits_needed(3), 2);
        assert_eq!(bits_needed(4), 2);
        assert_eq!(bits_needed(5), 3);
        assert_eq!(bits_needed(255), 8);
        assert_eq!(bits_needed(256), 8);
        assert_eq!(bits_needed(257), 9);
    }
}
