mod cf1;
mod codec;
#[allow(dead_code)] // GeoJSON extraction kept for later, no CLI entry
mod extract;
mod iso;
pub mod probe;
mod tools;

use std::io;
use std::path::PathBuf;

use clap::{Parser, Subcommand};

const DEFAULT_ISO: &str = "../dataset/NAV_DB_21708.ISO";

#[derive(Parser)]
#[command(name = "carindb-rs", about = "CarinDB navigation disc toolkit")]
struct Cli {
    /// Path to the navigation ISO
    #[arg(long, global = true, default_value = DEFAULT_ISO)]
    iso: String,
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand)]
enum Cmd {
    /// Dump every decoded block of a type to files
    DumpType {
        /// BLOCK_TYPE in hex, e.g. 0x18
        #[arg(value_parser = parse_hex_u16)]
        type_hex: u16,
        /// Output dir (default: dump_0xNN)
        #[arg(long)]
        out: Option<PathBuf>,
    },
    /// Decode one block (by absolute CARINdb sector) to a file; no disc scan
    DumpBlock {
        /// Absolute CARINdb sector (BLOCK_ID >> 8), decimal or 0x-prefixed hex
        #[arg(value_parser = parse_sector)]
        sector: usize,
        /// Output file (default: block_<sector>.bin)
        #[arg(long)]
        out: Option<PathBuf>,
    },
    /// Cross-instance length and per-offset statistics for a block type
    Stats {
        #[arg(value_parser = parse_hex_u16)]
        type_hex: u16,
        /// Machine-readable output
        #[arg(long)]
        json: bool,
    },
    /// Find every byte-aligned big-endian occurrence of a BLOCK_ID in decoded blocks
    Xref {
        /// One or more BLOCK_IDs in hex: (sector << 8) | length_in_sectors (single disc pass)
        #[arg(value_parser = parse_hex_u32, required = true)]
        block_id_hex: Vec<u32>,
    },
}

fn strip_hex(s: &str) -> &str {
    s.strip_prefix("0x").or_else(|| s.strip_prefix("0X")).unwrap_or(s)
}

fn parse_hex_u16(s: &str) -> Result<u16, String> {
    u16::from_str_radix(strip_hex(s), 16).map_err(|e| e.to_string())
}

fn parse_sector(s: &str) -> Result<usize, String> {
    match s.strip_prefix("0x").or_else(|| s.strip_prefix("0X")) {
        Some(h) => usize::from_str_radix(h, 16),
        None => s.parse(),
    }
    .map_err(|e| e.to_string())
}

fn parse_hex_u32(s: &str) -> Result<u32, String> {
    u32::from_str_radix(strip_hex(s), 16).map_err(|e| e.to_string())
}

fn main() -> io::Result<()> {
    let cli = Cli::parse();
    match cli.cmd {
        Cmd::DumpType { type_hex, out } => tools::dump_type(&cli.iso, type_hex, out.as_deref()),
        Cmd::DumpBlock { sector, out } => tools::dump_block(&cli.iso, sector, out.as_deref()),
        Cmd::Stats { type_hex, json } => tools::stats(&cli.iso, type_hex, json),
        Cmd::Xref { block_id_hex } => tools::xref(&cli.iso, &block_id_hex),
    }
}
