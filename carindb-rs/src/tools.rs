//! Block analysis subcommands: dump-type, stats, xref.

use std::collections::BTreeMap;
use std::fs;
use std::io;
use std::path::Path;

use crate::codec::{Decoded, decode_block};
use crate::iso::CarinVolume;

/// Open the volume; calibrate CF=1 sub-revision only when `need_cf1` (type 0x00 decode).
pub fn open(iso_path: &str, need_cf1: bool) -> io::Result<CarinVolume> {
    let image = crate::iso::IsoImage::new(iso_path)?;
    let mut vol = CarinVolume::new(image)?;
    std::panic::set_hook(Box::new(|_| {})); // decoder panics are caught and reported per block
    eprintln!("db_rel = {}", vol.db_rel);
    if need_cf1 {
        eprintln!("CF=1 sub-revision: {}", vol.calibrate(48));
    }
    Ok(vol)
}

#[derive(Default)]
struct LenStats {
    n: u64,
    total: u64,
    min: usize,
    max: usize,
    hist: BTreeMap<usize, u64>,
}

impl LenStats {
    fn add(&mut self, len: usize) {
        if self.n == 0 || len < self.min { self.min = len; }
        self.max = self.max.max(len);
        self.n += 1;
        self.total += len as u64;
        *self.hist.entry(len).or_default() += 1;
    }
    fn mean(&self) -> f64 { if self.n == 0 { 0.0 } else { self.total as f64 / self.n as f64 } }
    fn mode(&self) -> Option<(usize, u64)> {
        // smallest length wins ties
        self.hist.iter().fold(None, |best, (&l, &c)| match best {
            Some((_, bc)) if bc >= c => best,
            _ => Some((l, c)),
        })
    }
}

/// Tally of blocks that could not be decoded.
#[derive(Default)]
struct Skipped {
    cf1: u64,
    failed: u64,
    cf1_types: BTreeMap<u16, u64>,
    first_errors: Vec<String>,
}

impl Skipped {
    fn fail(&mut self, sector: u32, msg: String) {
        self.failed += 1;
        if self.first_errors.len() < 5 {
            self.first_errors.push(format!("sector {sector:#x}: {msg}"));
        }
    }
    fn cf1(&mut self, btype: u16) {
        self.cf1 += 1;
        *self.cf1_types.entry(btype).or_default() += 1;
    }
}

// ---------------------------------------------------------------- dump-type

pub fn dump_type(iso_path: &str, btype: u16, out: Option<&Path>) -> io::Result<()> {
    let vol = open(iso_path, true)?;
    let dir = out.map(Path::to_path_buf).unwrap_or_else(|| format!("dump_{btype:#04x}").into());
    fs::create_dir_all(&dir)?;

    let mut stats = LenStats::default();
    let (mut n_raw, mut n_cf2, mut n_cf1_dec, mut n_cf1_raw) = (0u64, 0u64, 0u64, 0u64);
    let mut skipped = Skipped::default();

    for blk in vol.iter_blocks().filter(|b| b.btype == btype) {
        let stem = format!("sector_{:08x}", blk.sector);
        match decode_block(&blk, &vol) {
            Decoded::Data(d) => {
                match blk.comp { 0 => n_raw += 1, 1 => n_cf1_dec += 1, _ => n_cf2 += 1 }
                fs::write(dir.join(format!("{stem}.bin")), &d)?;
                stats.add(d.len());
            }
            Decoded::Cf1Undecoded(raw) => {
                n_cf1_raw += 1;
                fs::write(dir.join(format!("{stem}.cf1raw.bin")), raw)?;
                stats.add(raw.len());
            }
            Decoded::Failed(msg) => skipped.fail(blk.sector, msg),
        }
    }

    println!("type {btype:#04x} -> {}", dir.display());
    println!("blocks written: {}  (CF=0: {n_raw}, CF=2: {n_cf2}, CF=1 decoded: {n_cf1_dec}, CF=1 raw: {n_cf1_raw})", stats.n);
    if n_cf1_raw > 0 {
        println!("NOTE: no CF=1 decoder for type {btype:#04x}; {n_cf1_raw} block(s) dumped as raw COMPRESSED bytes (*.cf1raw.bin, header included)");
    }
    if skipped.failed > 0 {
        println!("WARNING: {} block(s) failed to decode (not written):", skipped.failed);
        for e in &skipped.first_errors { println!("  {e}"); }
    }
    if stats.n > 0 {
        println!("total bytes: {}  len min/max/mean: {}/{}/{:.1}", stats.total, stats.min, stats.max, stats.mean());
    }
    Ok(())
}

// -------------------------------------------------------------------- stats

fn entropy(counts: &[u32; 256], n: u32) -> f64 {
    let n = n as f64;
    counts.iter().filter(|&&c| c > 0).map(|&c| { let p = c as f64 / n; -p * p.log2() }).sum()
}

pub fn stats(iso_path: &str, btype: u16, json: bool) -> io::Result<()> {
    let vol = open(iso_path, true)?;
    let mut lens = LenStats::default();
    // per-offset byte histogram over all instances that reach that offset
    let mut hist: Vec<[u32; 256]> = Vec::new();
    let mut skipped = Skipped::default();

    for blk in vol.iter_blocks().filter(|b| b.btype == btype) {
        match decode_block(&blk, &vol) {
            Decoded::Data(d) => {
                lens.add(d.len());
                if hist.len() < d.len() { hist.resize(d.len(), [0; 256]); }
                for (h, &b) in hist.iter_mut().zip(d.iter()) { h[b as usize] += 1; }
            }
            Decoded::Cf1Undecoded(_) => skipped.cf1(blk.btype),
            Decoded::Failed(m) => skipped.fail(blk.sector, m),
        }
    }

    if lens.n == 0 {
        println!("no decodable blocks of type {btype:#04x} (cf1 skipped: {}, failed: {})", skipped.cf1, skipped.failed);
        return Ok(());
    }

    // Analyse offsets covered by every instance.
    let common = lens.min;
    let n = lens.n as u32;
    struct Row { start: usize, end: usize, class: &'static str, value: Option<Vec<u8>>, hmin: f64, hmax: f64 }
    let mut rows: Vec<Row> = Vec::new();
    let mut per_offset = Vec::with_capacity(common);
    for off in 0..common {
        let h = entropy(&hist[off], n);
        let (class, byte) = if h == 0.0 {
            ("constant", hist[off].iter().position(|&c| c > 0).map(|b| b as u8))
        } else if h < 2.0 { ("low-var", None) } else { ("varies", None) };
        per_offset.push((h, class, byte));
        match rows.last_mut() {
            Some(r) if r.class == class && class != "constant" => { r.end = off; r.hmin = r.hmin.min(h); r.hmax = r.hmax.max(h); }
            Some(r) if r.class == "constant" && class == "constant" => { r.end = off; r.value.as_mut().unwrap().push(byte.unwrap()); }
            _ => rows.push(Row { start: off, end: off, class, value: byte.map(|b| vec![b]), hmin: h, hmax: h }),
        }
    }

    let mode = lens.mode().unwrap();
    if json {
        let hist_json: serde_json::Map<String, serde_json::Value> =
            lens.hist.iter().map(|(l, c)| (l.to_string(), (*c).into())).collect();
        let offs: Vec<_> = per_offset.iter().enumerate().map(|(o, (h, c, b))| serde_json::json!({
            "offset": o, "class": c, "entropy_bits": h, "value": b })).collect();
        let doc = serde_json::json!({
            "type": btype, "instances": lens.n,
            "length": { "min": lens.min, "max": lens.max, "mean": lens.mean(), "mode": mode.0, "mode_count": mode.1, "histogram": hist_json },
            "analysed_offsets": common, "offsets": offs,
            "skipped": { "cf1_undecoded": skipped.cf1, "failed": skipped.failed },
        });
        println!("{}", serde_json::to_string_pretty(&doc).unwrap());
        return Ok(());
    }

    println!("type {btype:#04x}: {} instances (skipped: {} CF=1 undecoded, {} failed)", lens.n, skipped.cf1, skipped.failed);
    println!("length: min {} max {} mean {:.1} mode {} (x{})", lens.min, lens.max, lens.mean(), mode.0, mode.1);
    let mut top: Vec<_> = lens.hist.iter().collect();
    top.sort_by(|a, b| b.1.cmp(a.1).then(a.0.cmp(b.0)));
    println!("top lengths:");
    for (l, c) in top.iter().take(10) { println!("  {l:>7} B  x{c}"); }
    println!("\nper-offset analysis over first {common} bytes (shortest instance):");
    println!("{:<15} {:<9} {}", "offsets", "class", "detail");
    for r in &rows {
        let range = if r.start == r.end { format!("{:#06x}", r.start) } else { format!("{:#06x}-{:#06x}", r.start, r.end) };
        let detail = match (&r.value, r.class) {
            (Some(v), _) if v.len() <= 16 => format!("= {}", v.iter().map(|b| format!("{b:02x}")).collect::<Vec<_>>().join(" ")),
            (Some(v), _) => format!("{} constant bytes", v.len()),
            _ => format!("entropy {:.2}..{:.2} bits", r.hmin, r.hmax),
        };
        println!("{range:<15} {:<9} {detail}", r.class);
    }
    Ok(())
}

// --------------------------------------------------------------------- xref

pub fn xref(iso_path: &str, block_ids: &[u32]) -> io::Result<()> {
    let vol = open(iso_path, true)?;
    let pats: Vec<[u8; 4]> = block_ids.iter().map(|id| id.to_be_bytes()).collect();
    let mut per_id = vec![0u64; pats.len()];
    let mut scanned = 0u64;
    let mut skipped = Skipped::default();

    for blk in vol.iter_blocks() {
        let d = match decode_block(&blk, &vol) {
            Decoded::Data(d) => d,
            Decoded::Cf1Undecoded(_) => { skipped.cf1(blk.btype); continue; }
            Decoded::Failed(m) => { skipped.fail(blk.sector, m); continue; }
        };
        scanned += 1;
        for (off, w) in d.windows(4).enumerate() {
            for (i, pat) in pats.iter().enumerate() {
                // a block's own header holds its BLOCK_ID at offset 0: not a reference
                if w == pat && !(off == 0 && blk.sector == block_ids[i] >> 8) {
                    per_id[i] += 1;
                    println!("id={:#010x} type={:#04x} sector={:#010x} offset={:#06x}", block_ids[i], blk.btype, blk.sector, off);
                }
            }
        }
    }

    eprintln!("\nscanned {scanned} blocks (byte-aligned, big-endian)");
    for (id, n) in block_ids.iter().zip(&per_id) { eprintln!("  {id:#010x}: {n} hit(s)"); }
    if skipped.cf1 > 0 {
        eprintln!("WARNING: {} CF=1 block(s) SKIPPED undecoded (possible false negatives), by type:", skipped.cf1);
        for (t, c) in &skipped.cf1_types { eprintln!("  {t:#04x}: {c}"); }
    }
    if skipped.failed > 0 {
        eprintln!("WARNING: {} block(s) failed to decode:", skipped.failed);
        for e in &skipped.first_errors { eprintln!("  {e}"); }
    }
    Ok(())
}
