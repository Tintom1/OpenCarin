use std::collections::HashMap;
use std::fs::File;
use std::io;
use std::path::Path;
use memmap2::{Mmap, MmapOptions};

pub const ISO_SECTOR: usize = 2048;
pub const CARIN_SECTOR: usize = 512;
pub const CARIN_WINDOW: usize = 0x400000;
pub const BLOCK_HDR_SIZE: usize = 8;

pub struct IsoImage {
    mmap: Mmap,
    pub files: HashMap<String, IsoFile>,
}

#[derive(Clone, Debug)]
pub struct IsoFile {
    pub path: String,
    pub lba: u32,
    pub size: u32,
}

impl IsoImage {
    pub fn new<P: AsRef<Path>>(path: P) -> io::Result<Self> {
        let file = File::open(path)?;
        let mmap = unsafe { MmapOptions::new().map(&file)? };
        
        let mut iso = IsoImage {
            mmap,
            files: HashMap::new(),
        };
        iso.read_pvd()?;
        Ok(iso)
    }

    fn read_pvd(&mut self) -> io::Result<()> {
        let pvd_offset = 16 * ISO_SECTOR;
        if self.mmap[pvd_offset] != 1 || &self.mmap[pvd_offset + 1..pvd_offset + 6] != b"CD001" {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "Not a valid ISO 9660 PVD"));
        }

        let root_dir_record = &self.mmap[pvd_offset + 156..pvd_offset + 190];
        let root_lba = u32::from_le_bytes(root_dir_record[2..6].try_into().unwrap());
        let root_size = u32::from_le_bytes(root_dir_record[10..14].try_into().unwrap());

        let root_files = self.walk(root_lba, root_size, "")?;
        self.files = root_files;
        Ok(())
    }

    fn walk(&self, lba: u32, size: u32, prefix: &str) -> io::Result<HashMap<String, IsoFile>> {
        let mut files = HashMap::new();
        let start = (lba as usize) * ISO_SECTOR;
        let end = start + (size as usize);
        let mut pos = start;

        while pos < end {
            let rec_len = self.mmap[pos] as usize;
            if rec_len == 0 {
                pos = (pos / ISO_SECTOR + 1) * ISO_SECTOR;
                continue;
            }
            if pos + 33 >= end { break; }

            let name_len = self.mmap[pos + 32] as usize;
            let name_bytes = &self.mmap[pos + 33..pos + 33 + name_len];
            let mut name = String::from_utf8_lossy(name_bytes).to_string();
            
            if name_len == 1 && (name == "\x00" || name == "\x01") {
                pos += rec_len;
                continue;
            }
            
            if let Some(semi) = name.find(';') {
                name.truncate(semi);
            }
            
            let full = if prefix.is_empty() {
                format!("/{}", name)
            } else {
                format!("{}/{}", prefix, name)
            };

            let flags = self.mmap[pos + 25];
            let ext_lba = u32::from_le_bytes(self.mmap[pos + 2..pos + 6].try_into().unwrap());
            let ext_size = u32::from_le_bytes(self.mmap[pos + 10..pos + 14].try_into().unwrap());

            if (flags & 0x02) != 0 {
                let sub_files = self.walk(ext_lba, ext_size, &full)?;
                files.extend(sub_files);
            } else {
                files.insert(full.clone(), IsoFile {
                    path: full,
                    lba: ext_lba,
                    size: ext_size,
                });
            }
            
            pos += rec_len;
        }

        Ok(files)
    }

    pub fn read_slice(&self, file: &IsoFile, offset: usize, length: usize) -> &[u8] {
        let file_start = (file.lba as usize) * ISO_SECTOR;
        let start = file_start + offset;
        let end = std::cmp::min(start + length, file_start + file.size as usize);
        &self.mmap[start..end]
    }
}

pub struct CarinVolume {
    pub image: IsoImage,
    parts: Vec<IsoFile>,
    sectors: Vec<usize>,
    pub layout: Option<HashMap<u16, u16>>,
    pub db_rel: u16,
    pub subrel: u16,
}

pub struct CarinBlock<'a> {
    pub sector: u32,
    pub length: u8,
    pub btype: u16,
    pub comp: u8,
    pub usize_: u8,
    pub raw: &'a [u8],
}

impl CarinVolume {
    pub fn new(image: IsoImage) -> io::Result<Self> {
        let db_0 = image.files.get("/DB/DB_0").cloned().ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "DB_0 not found"))?;
        let db_1 = image.files.get("/DB/DB_1").cloned().ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "DB_1 not found"))?;
        let parts = vec![db_0.clone(), db_1.clone()];
        let sectors = vec![
            (db_0.size as usize) / CARIN_SECTOR,
            (db_1.size as usize) / CARIN_SECTOR,
        ];
        
        let mut vol = CarinVolume {
            image,
            parts,
            sectors,
            layout: None,
            db_rel: 0,
            subrel: 9,
        };
        
        vol.read_layout();
        
        Ok(vol)
    }

    fn read_layout(&mut self) {
        let mut layout = HashMap::new();
        let db_rel;
        {
            let sb = self.read_sectors(0, 2);
            let off = u16::from_be_bytes(sb[0x28..0x2A].try_into().unwrap()) as usize;
            let count = u16::from_be_bytes(sb[0x2A..0x2C].try_into().unwrap()) as usize;
            
            for i in 0..count {
                let p = off + i * 4;
                let key = u16::from_be_bytes(sb[p..p+2].try_into().unwrap());
                let val = u16::from_be_bytes(sb[p+2..p+4].try_into().unwrap());
                layout.insert(key, val);
            }
            db_rel = u16::from_be_bytes(sb[0x1A..0x1C].try_into().unwrap());
        }
        self.layout = Some(layout);
        self.db_rel = db_rel;
    }

    pub fn layout(&self) -> &HashMap<u16, u16> {
        self.layout.as_ref().unwrap()
    }

    pub fn read_sectors(&self, sector: usize, count: usize) -> &[u8] {
        let idx = sector / CARIN_WINDOW;
        let local = sector % CARIN_WINDOW;
        self.image.read_slice(&self.parts[idx], local * CARIN_SECTOR, count * CARIN_SECTOR)
    }

    pub fn block(&self, sector: usize) -> Option<CarinBlock> {
        let head = self.read_sectors(sector, 1);
        if head.len() < BLOCK_HDR_SIZE { return None; }
        
        let bid = u32::from_be_bytes(head[0..4].try_into().unwrap());
        let btype = u16::from_be_bytes(head[4..6].try_into().unwrap());
        let comp = head[6];
        let usize_ = head[7];
        
        let length = (bid & 0xFF) as usize;
        if length == 0 { return None; }
        
        let raw = self.read_sectors(sector, length);
        
        Some(CarinBlock {
            sector: sector as u32,
            length: length as u8,
            btype,
            comp,
            usize_,
            raw,
        })
    }

    pub fn calibrate(&mut self, sample_size: usize) -> u16 {
        let mut heads = Vec::new();
        let mut count = 0;
        let max_scans = 10000;
        
        // Cannot use iter_blocks() mutably while self is mutably borrowed easily here, 
        // but we can manually iterate or clone parts.
        // For simplicity, we just collect some blocks.
        let mut iter = self.iter_blocks();
        while let Some(blk) = iter.next() {
            if blk.btype == 0x00 && (blk.comp & 1) != 0 {
                // read_sectors does not take mut self.
                heads.push((blk.sector, blk.length, blk.usize_));
            }
            count += 1;
            if count >= max_scans || heads.len() >= sample_size * 10 {
                break;
            }
        }
        
        if heads.is_empty() {
            return self.subrel;
        }
        
        let step = std::cmp::max(1, heads.len() / sample_size);
        let mut raws_owned = Vec::new();
        for i in (0..heads.len()).step_by(step).take(sample_size) {
            let (sec, len, _) = heads[i];
            raws_owned.push(self.read_sectors(sec as usize, len as usize).to_vec());
        }
        
        let mut raws = Vec::new();
        for r in &raws_owned {
            raws.push(r.as_slice());
        }
        
        let layout = self.layout().clone();
        let best_subrel = crate::probe::detect_subrel(&raws, &layout, self.db_rel);
        self.subrel = best_subrel;
        self.subrel
    }
}

pub struct BlockIter<'a> {
    vol: &'a CarinVolume,
    current_part: usize,
    current_sector: usize,
}

impl<'a> CarinVolume {
    pub fn iter_blocks(&'a self) -> BlockIter<'a> {
        BlockIter {
            vol: self,
            current_part: 0,
            current_sector: 0,
        }
    }
}

impl<'a> Iterator for BlockIter<'a> {
    type Item = CarinBlock<'a>;

    fn next(&mut self) -> Option<Self::Item> {
        while self.current_part < self.vol.parts.len() {
            let base = self.current_part * CARIN_WINDOW;
            let nsec = self.vol.sectors[self.current_part];
            
            while self.current_sector < nsec {
                let absolute_sector = base + self.current_sector;
                let head = self.vol.read_sectors(absolute_sector, 1);
                if head.len() < 8 {
                    self.current_sector += 1;
                    continue;
                }
                
                let bid = u32::from_be_bytes(head[0..4].try_into().unwrap());
                let btype = u16::from_be_bytes(head[4..6].try_into().unwrap());
                let comp = head[6];
                let usize_ = head[7];
                
                let length = (bid & 0xFF) as usize;
                
                if (bid >> 8) != absolute_sector as u32 || length == 0 {
                    self.current_sector += 1;
                    continue;
                }
                
                let raw = self.vol.read_sectors(absolute_sector, length);
                
                self.current_sector += length;
                
                return Some(CarinBlock {
                    sector: absolute_sector as u32,
                    length: length as u8,
                    btype,
                    comp,
                    usize_,
                    raw,
                });
            }
            self.current_part += 1;
            self.current_sector = 0;
        }
        None
    }
}
