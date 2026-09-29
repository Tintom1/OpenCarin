use std::collections::HashMap;

pub fn shape_pointer_score(data: &[u8], table: &HashMap<u16, u16>) -> Option<f32> {
    let desc = table.get(&0x05).copied().unwrap_or(8) as usize;
    let rec4 = table.get(&0x08).copied().unwrap_or(0) as usize;
    let rec7 = table.get(&0x0c).copied().unwrap_or(6) as usize;
    
    if rec4 == 0 || data.len() < desc + 32 {
        return None;
    }
    
    let s4 = u16::from_be_bytes(data[desc + 4 * 4..desc + 4 * 4 + 2].try_into().unwrap()) as usize;
    let n4 = u16::from_be_bytes(data[desc + 4 * 4 + 2..desc + 4 * 4 + 4].try_into().unwrap()) as usize;
    
    let s7 = u16::from_be_bytes(data[desc + 7 * 4..desc + 7 * 4 + 2].try_into().unwrap()) as usize;
    let n7 = u16::from_be_bytes(data[desc + 7 * 4 + 2..desc + 7 * 4 + 4].try_into().unwrap()) as usize;
    
    if n4 < 3 || n7 < 3 || s4 + rec4 * n4 > data.len() {
        return None;
    }
    
    let mut ptrs = Vec::with_capacity(n4);
    for i in 0..n4 {
        let off = s4 + rec4 * i + 4;
        let p = u16::from_be_bytes(data[off..off+2].try_into().unwrap()) as usize;
        ptrs.push(p);
    }
    
    let end7 = s7 + rec7 * n7;
    
    let mut mono = 0.0;
    for w in ptrs.windows(2) {
        if w[0] <= w[1] { mono += 1.0; }
    }
    mono /= (n4 - 1) as f32;
    
    let mut inside = 0.0;
    for &p in &ptrs {
        if p >= s7 && p <= end7 { inside += 1.0; }
    }
    inside /= n4 as f32;
    
    let mut steps = Vec::new();
    for w in ptrs.windows(2) {
        if w[1] != w[0] { steps.push(w[1].saturating_sub(w[0])); }
    }
    
    let whole = if steps.is_empty() {
        1.0
    } else {
        let mut count = 0.0;
        for &s in &steps {
            if s % rec7 == 0 { count += 1.0; }
        }
        count / (steps.len() as f32)
    };
    
    Some((mono + inside + whole) / 3.0)
}

pub fn name_pointer_score(data: &[u8], table: &HashMap<u16, u16>) -> Option<f32> {
    let desc = table.get(&0x05).copied().unwrap_or(8) as usize;
    let rec2 = table.get(&0x40).copied().unwrap_or(0) as usize;
    
    if rec2 == 0 || data.len() < desc + 12 {
        return None;
    }
    
    let s2 = u16::from_be_bytes(data[desc + 2 * 4..desc + 2 * 4 + 2].try_into().unwrap()) as usize;
    let n2 = u16::from_be_bytes(data[desc + 2 * 4 + 2..desc + 2 * 4 + 4].try_into().unwrap()) as usize;
    
    if s2 + rec2 * n2 > data.len() {
        return None;
    }
    
    let mut ptrs = Vec::new();
    for i in 0..n2 {
        let off = s2 + rec2 * i;
        let p = u16::from_be_bytes(data[off..off+2].try_into().unwrap()) as usize;
        if p > 0 { ptrs.push(p); }
    }
    
    if ptrs.len() < 3 { return None; }
    
    let is_string = |p: usize| -> bool {
        if p == 0 || p >= data.len() || data[p - 1] != 0 { return false; }
        let mut end = p;
        while end < data.len() && data[end] != 0 { end += 1; }
        if end == p || end >= data.len() { return false; }
        for i in p..end {
            let c = data[i];
            if c < 0x20 || c == 0x7F { return false; }
        }
        true
    };
    
    let mut hits = 0.0;
    for &p in &ptrs {
        if is_string(p) { hits += 1.0; }
    }
    
    Some(hits / (ptrs.len() as f32))
}

pub fn detect_subrel(raws: &[&[u8]], table: &HashMap<u16, u16>, dbrel: u16) -> u16 {
    use std::panic;
    
    let candidates = [8, 9];
    let mut best = 9;
    let mut best_score = -1.0;
    
    for &subrel in &candidates {
        let mut scores = Vec::new();
        for &raw in raws {
            let result = panic::catch_unwind(|| {
                crate::cf1::decode_block(raw, table, dbrel, subrel)
            });
            
            match result {
                Ok(data) => {
                    let mut parts = Vec::new();
                    if let Some(s) = shape_pointer_score(&data, table) { parts.push(s); }
                    if let Some(s) = name_pointer_score(&data, table) { parts.push(s); }
                    
                    if !parts.is_empty() {
                        let avg = parts.iter().sum::<f32>() / (parts.len() as f32);
                        scores.push(avg);
                    }
                }
                Err(_) => {
                    scores.push(0.0);
                }
            }
        }
        
        if !scores.is_empty() {
            let avg = scores.iter().sum::<f32>() / (scores.len() as f32);
            if avg > best_score {
                best_score = avg;
                best = subrel;
            }
        }
    }
    
    best
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    #[test]
    fn test_shape_pointer_score_empty() {
        let data = vec![0; 100];
        let mut table = HashMap::new();
        table.insert(0x05, 8);
        table.insert(0x08, 32);
        table.insert(0x0c, 6);
        let score = shape_pointer_score(&data, &table);
        assert!(score.is_none() || score.unwrap() == 0.0);
    }
}
