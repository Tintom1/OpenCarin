//! Generic block decoding: dispatches on COMPRESSION_FLAG.

use std::borrow::Cow;
use std::io::{self, Read};
use std::panic::{AssertUnwindSafe, catch_unwind};

use flate2::read::ZlibDecoder;

use crate::cf1;
use crate::iso::{BLOCK_HDR_SIZE, CarinBlock, CarinVolume};

/// Inflate a CF=2 block. The zlib stream starts right after the 8-byte header
/// (the section descriptor is inside the compressed payload). Returns the
/// decompressed block with the original 8-byte header prepended, like the
/// Python `CarinBlock.parse`.
pub fn decode_cf2(raw: &[u8]) -> io::Result<Vec<u8>> {
    if raw.len() < BLOCK_HDR_SIZE {
        return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "block shorter than header"));
    }
    let mut out = Vec::with_capacity(raw[7] as usize * 512);
    out.extend_from_slice(&raw[..BLOCK_HDR_SIZE]);
    ZlibDecoder::new(&raw[BLOCK_HDR_SIZE..]).read_to_end(&mut out)?;
    Ok(out)
}

pub enum Decoded<'a> {
    /// Fully decoded block, header included.
    Data(Cow<'a, [u8]>),
    /// CF=1 of a type with no decoder yet; carries the raw compressed bytes.
    Cf1Undecoded(&'a [u8]),
    /// Unknown CF or inflate failure.
    Failed(String),
}

pub fn decode_block<'a>(blk: &CarinBlock<'a>, vol: &CarinVolume) -> Decoded<'a> {
    match blk.comp {
        0 => Decoded::Data(Cow::Borrowed(blk.raw)),
        1 if cf1::supports(blk.btype) => {
            // the decoder panics on malformed streams (Python raises); report instead of aborting a scan
            match catch_unwind(AssertUnwindSafe(|| cf1::decode_block(blk.raw, vol.layout(), vol.db_rel, vol.subrel))) {
                Ok(d) => Decoded::Data(Cow::Owned(d)),
                Err(e) => {
                    let msg = e.downcast_ref::<String>().cloned()
                        .or_else(|| e.downcast_ref::<&str>().map(|s| s.to_string()))
                        .unwrap_or_default();
                    Decoded::Failed(format!("cf1 decoder panicked: {msg}"))
                }
            }
        }
        1 => Decoded::Cf1Undecoded(blk.raw),
        2 => match decode_cf2(blk.raw) {
            Ok(d) => Decoded::Data(Cow::Owned(d)),
            Err(e) => Decoded::Failed(format!("zlib: {e}")),
        },
        cf => Decoded::Failed(format!("unknown CF={cf}")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use flate2::{Compression, write::ZlibEncoder};
    use std::io::Write;

    #[test]
    fn cf2_roundtrip() {
        let payload: Vec<u8> = (0..1000u32).map(|i| (i % 7) as u8).collect();
        let mut enc = ZlibEncoder::new(Vec::new(), Compression::best());
        enc.write_all(&payload).unwrap();
        let mut raw = vec![0, 0, 2, 1, 0x00, 0x13, 2, 2];
        raw.extend(enc.finish().unwrap());
        raw.resize(1024, 0); // sector padding
        let d = decode_cf2(&raw).unwrap();
        assert_eq!(&d[..8], &raw[..8]);
        assert_eq!(&d[8..], &payload[..]);
    }
}
