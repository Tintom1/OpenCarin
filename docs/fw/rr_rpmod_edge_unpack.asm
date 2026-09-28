; RoadRunner (RR, DVD) route planner `rpmod` — S4 road-segment unpacking.
; Source: NAV_SW(v32).iso /V_2/RR/0101/BMWC01S/app_sw/bsw2, OS-9000 module
; `rpmod` at bsw2+0x110cf0 (MIPS32 BE). Offsets are module-relative.
; Regenerate: python scripts/firmware/mips_listing.py \
;     build/fw/V_2_RR_0101_BMWC01S_app_sw_bsw2 rpmod build/rr_rpmod.asm
; Notes: docs/fw/04-rr-rpmod-edge-record.md
;
; Register conventions in sub_01fd80:
;   $s0 = edge struct (out)     $s1 = decoded 0x00..0x03 block (header incl.)
;   $s2 = S4 segment record     $s3/$s4 = start/end node record
;   gp[-0x6064] -> DB descriptor: +0x14 = DB-REL, T[i] at +0x1e + 2*i
; ---- sub_01fd80
01fd80: afbf0000  sw       $ra, ($sp)
01fd84: 03a04025  move     $t0, $sp
01fd88: 27bdffd0  addiu    $sp, $sp, -0x30
01fd8c: afa80004  sw       $t0, 4($sp)
01fd90: afb40018  sw       $s4, 0x18($sp)
01fd94: afb3001c  sw       $s3, 0x1c($sp)
01fd98: afb20020  sw       $s2, 0x20($sp)
01fd9c: afb10024  sw       $s1, 0x24($sp)
01fda0: afb00028  sw       $s0, 0x28($sp)
01fda4: 00808025  move     $s0, $a0
01fda8: 96080008  lhu      $t0, 8($s0)
01fdac: 00a08825  move     $s1, $a1
01fdb0: 02289021  addu     $s2, $s1, $t0
01fdb4: 9648000c  lhu      $t0, 0xc($s2)
01fdb8: ae080010  sw       $t0, 0x10($s0)
01fdbc: 92480010  lbu      $t0, 0x10($s2)
01fdc0: 3108000f  andi     $t0, $t0, 0xf
01fdc4: a2080017  sb       $t0, 0x17($s0)
01fdc8: 9248000b  lbu      $t0, 0xb($s2)
01fdcc: 3108000f  andi     $t0, $t0, 0xf
01fdd0: a2080016  sb       $t0, 0x16($s0)
01fdd4: 92480011  lbu      $t0, 0x11($s2)
01fdd8: 3108000f  andi     $t0, $t0, 0xf
01fddc: a2080014  sb       $t0, 0x14($s0)
01fde0: 9248000b  lbu      $t0, 0xb($s2)
01fde4: 31080030  andi     $t0, $t0, 0x30
01fde8: 00084102  srl      $t0, $t0, 4
01fdec: a2080015  sb       $t0, 0x15($s0)
01fdf0: 92480010  lbu      $t0, 0x10($s2)
01fdf4: 31080070  andi     $t0, $t0, 0x70
01fdf8: 00084102  srl      $t0, $t0, 4
01fdfc: a2080019  sb       $t0, 0x19($s0)
01fe00: 92480011  lbu      $t0, 0x11($s2)
01fe04: 310800f0  andi     $t0, $t0, 0xf0
01fe08: 00084102  srl      $t0, $t0, 4
01fe0c: a2080018  sb       $t0, 0x18($s0)
01fe10: 9248000e  lbu      $t0, 0xe($s2)
01fe14: a2080026  sb       $t0, 0x26($s0)
01fe18: 9248000f  lbu      $t0, 0xf($s2)
01fe1c: a2080027  sb       $t0, 0x27($s0)
01fe20: 96480000  lhu      $t0, ($s2)
01fe24: a6080022  sh       $t0, 0x22($s0)
01fe28: 96480002  lhu      $t0, 2($s2)
01fe2c: a6080024  sh       $t0, 0x24($s0)
01fe30: 96080022  lhu      $t0, 0x22($s0)
01fe34: 02289821  addu     $s3, $s1, $t0
01fe38: 96080024  lhu      $t0, 0x24($s0)
01fe3c: 0228a021  addu     $s4, $s1, $t0
01fe40: 3c080000  lui      $t0, 0
01fe44: 011c4021  addu     $t0, $t0, $gp
01fe48: 8d089f9c  lw       $t0, -0x6064($t0)
01fe4c: 95090028  lhu      $t1, 0x28($t0)
01fe50: 95080040  lhu      $t0, 0x40($t0)
01fe54: 01284021  addu     $t0, $t1, $t0
01fe58: 02282021  addu     $a0, $s1, $t0
01fe5c: 3c080000  lui      $t0, 0
01fe60: 011c4021  addu     $t0, $t0, $gp
01fe64: 8d08831c  lw       $t0, -0x7ce4($t0)
01fe68: 02602825  move     $a1, $s3
01fe6c: 0100f809  jalr     $t0
01fe70: 2606002c  addiu    $a2, $s0, 0x2c
01fe74: 3c080000  lui      $t0, 0
01fe78: 011c4021  addu     $t0, $t0, $gp
01fe7c: 8d089f9c  lw       $t0, -0x6064($t0)
01fe80: 95090028  lhu      $t1, 0x28($t0)
01fe84: 95080040  lhu      $t0, 0x40($t0)
01fe88: 01284021  addu     $t0, $t1, $t0
01fe8c: 02282021  addu     $a0, $s1, $t0
01fe90: 3c080000  lui      $t0, 0
01fe94: 011c4021  addu     $t0, $t0, $gp
01fe98: 8d08831c  lw       $t0, -0x7ce4($t0)
01fe9c: 02802825  move     $a1, $s4
01fea0: 0100f809  jalr     $t0
01fea4: 26060034  addiu    $a2, $s0, 0x34
01fea8: 92680006  lbu      $t0, 6($s3)
01feac: 92890006  lbu      $t1, 6($s4)
01feb0: 240a0001  addiu    $t2, $zero, 1
01feb4: 31080007  andi     $t0, $t0, 7
01feb8: 31290007  andi     $t1, $t1, 7
01febc: 510a0002  beql     $t0, $t2, 0x1fec8
01fec0: 24080001  addiu    $t0, $zero, 1
01fec4: 00004025  move     $t0, $zero
01fec8: a2080028  sb       $t0, 0x28($s0)
01fecc: 24080001  addiu    $t0, $zero, 1
01fed0: 51280002  beql     $t1, $t0, 0x1fedc
01fed4: 24080001  addiu    $t0, $zero, 1
01fed8: 00004025  move     $t0, $zero
01fedc: a2080029  sb       $t0, 0x29($s0)
01fee0: 92680006  lbu      $t0, 6($s3)
01fee4: 310800c0  andi     $t0, $t0, 0xc0
01fee8: 24090003  addiu    $t1, $zero, 3
01feec: 00084182  srl      $t0, $t0, 6
01fef0: 01284023  subu     $t0, $t1, $t0
01fef4: a208003c  sb       $t0, 0x3c($s0)
01fef8: 92880006  lbu      $t0, 6($s4)
01fefc: 310800c0  andi     $t0, $t0, 0xc0
01ff00: 00084182  srl      $t0, $t0, 6
01ff04: 01284023  subu     $t0, $t1, $t0
01ff08: a208003d  sb       $t0, 0x3d($s0)
01ff0c: 92080017  lbu      $t0, 0x17($s0)
01ff10: 24090006  addiu    $t1, $zero, 6
01ff14: 51090010  beql     $t0, $t1, 0x1ff58
01ff18: 00004025  move     $t0, $zero
01ff1c: 92080014  lbu      $t0, 0x14($s0)
01ff20: 24090003  addiu    $t1, $zero, 3
01ff24: 51090006  beql     $t0, $t1, 0x1ff40
01ff28: 92080018  lbu      $t0, 0x18($s0)
01ff2c: 92080014  lbu      $t0, 0x14($s0)
01ff30: 24090004  addiu    $t1, $zero, 4
01ff34: 15090004  bne      $t0, $t1, 0x1ff48
01ff38: 00000000  nop      
01ff3c: 92080018  lbu      $t0, 0x18($s0)
01ff40: 24090004  addiu    $t1, $zero, 4
01ff44: 15090003  bne      $t0, $t1, 0x1ff54
01ff48: 24080001  addiu    $t0, $zero, 1
01ff4c: 10000002  b        0x1ff58
01ff50: 00000000  nop      
01ff54: 00004025  move     $t0, $zero
01ff58: a208001b  sb       $t0, 0x1b($s0)
01ff5c: 96290004  lhu      $t1, 4($s1)
01ff60: 3c080000  lui      $t0, 0
01ff64: 011c4021  addu     $t0, $t0, $gp
01ff68: 00094880  sll      $t1, $t1, 2
01ff6c: 250885d0  addiu    $t0, $t0, -0x7a30
01ff70: 01094021  addu     $t0, $t0, $t1
01ff74: 91080003  lbu      $t0, 3($t0)
01ff78: a208001c  sb       $t0, 0x1c($s0)
01ff7c: 9248000b  lbu      $t0, 0xb($s2)
01ff80: 31080040  andi     $t0, $t0, 0x40
01ff84: 24090004  addiu    $t1, $zero, 4
01ff88: 00084102  srl      $t0, $t0, 4
01ff8c: 51090002  beql     $t0, $t1, 0x1ff98
01ff90: 24080001  addiu    $t0, $zero, 1
01ff94: 00004025  move     $t0, $zero
01ff98: 3c010007  lui      $at, 7
01ff9c: 242133a0  addiu    $at, $at, 0x33a0   ; -> sub_07b390
01ffa0: 003e0821  addu     $at, $at, $fp
01ffa4: 0020f809  jalr     $at
01ffa8: a208001e  sb       $t0, 0x1e($s0)
01ffac: 2848001b  slti     $t0, $v0, 0x1b
01ffb0: 55000005  bnel     $t0, $zero, 0x1ffc8
01ffb4: 24080001  addiu    $t0, $zero, 1
01ffb8: 92480018  lbu      $t0, 0x18($s2)
01ffbc: 10000002  b        0x1ffc8
01ffc0: 31080010  andi     $t0, $t0, 0x10
01ffc4: 24080001  addiu    $t0, $zero, 1
01ffc8: 24090010  addiu    $t1, $zero, 0x10
01ffcc: 51090002  beql     $t0, $t1, 0x1ffd8
01ffd0: 24080001  addiu    $t0, $zero, 1
01ffd4: 00004025  move     $t0, $zero
01ffd8: a208001f  sb       $t0, 0x1f($s0)
01ffdc: 9208001c  lbu      $t0, 0x1c($s0)
01ffe0: 15000024  bnez     $t0, 0x20074
01ffe4: 3c010007  lui      $at, 7
01ffe8: 242133a0  addiu    $at, $at, 0x33a0   ; -> sub_07b390
01ffec: 003e0821  addu     $at, $at, $fp
01fff0: 0020f809  jalr     $at
01fff4: 00000000  nop      
01fff8: 28480015  slti     $t0, $v0, 0x15
01fffc: 55000006  bnel     $t0, $zero, 0x20018
020000: 3c090000  lui      $t1, 0
020004: 9248000a  lbu      $t0, 0xa($s2)
020008: 31080080  andi     $t0, $t0, 0x80
02000c: 1000000a  b        0x20038
020010: 00084102  srl      $t0, $t0, 4
020014: 3c090000  lui      $t1, 0
020018: 013c4821  addu     $t1, $t1, $gp
02001c: 8d299f9c  lw       $t1, -0x6064($t1)
020020: 95290030  lhu      $t1, 0x30($t1)
020024: 02494821  addu     $t1, $s2, $t1
020028: 95290002  lhu      $t1, 2($t1)
02002c: 31290080  andi     $t1, $t1, 0x80
020030: 00094902  srl      $t1, $t1, 4
020034: 312800ff  andi     $t0, $t1, 0xff
020038: 24090008  addiu    $t1, $zero, 8
02003c: 51090002  beql     $t0, $t1, 0x20048
020040: 24080001  addiu    $t0, $zero, 1
020044: 00004025  move     $t0, $zero
020048: a208001a  sb       $t0, 0x1a($s0)
02004c: 3c080000  lui      $t0, 0
020050: 011c4021  addu     $t0, $t0, $gp
020054: 8d089f9c  lw       $t0, -0x6064($t0)
020058: 95080030  lhu      $t0, 0x30($t0)
02005c: 02484021  addu     $t0, $s2, $t0
020060: 95080002  lhu      $t0, 2($t0)
020064: 31080070  andi     $t0, $t0, 0x70
020068: 00084102  srl      $t0, $t0, 4
02006c: 10000014  b        0x200c0
020070: a2080020  sb       $t0, 0x20($s0)
020074: 3c010007  lui      $at, 7
020078: 242133a0  addiu    $at, $at, 0x33a0   ; -> sub_07b390
02007c: 003e0821  addu     $at, $at, $fp
020080: 0020f809  jalr     $at
020084: 00000000  nop      
020088: 28480015  slti     $t0, $v0, 0x15
02008c: 55000006  bnel     $t0, $zero, 0x200a8
020090: 00004025  move     $t0, $zero
020094: 9248000a  lbu      $t0, 0xa($s2)
020098: 31080080  andi     $t0, $t0, 0x80
02009c: 10000002  b        0x200a8
0200a0: 00084102  srl      $t0, $t0, 4
0200a4: 00004025  move     $t0, $zero
0200a8: 24090008  addiu    $t1, $zero, 8
0200ac: 51090002  beql     $t0, $t1, 0x200b8
0200b0: 24080001  addiu    $t0, $zero, 1
0200b4: 00004025  move     $t0, $zero
0200b8: a208001a  sb       $t0, 0x1a($s0)
0200bc: a2000020  sb       $zero, 0x20($s0)
0200c0: 92480010  lbu      $t0, 0x10($s2)
0200c4: 31080080  andi     $t0, $t0, 0x80
0200c8: 00084102  srl      $t0, $t0, 4
0200cc: 55000002  bnel     $t0, $zero, 0x200d8
0200d0: 24080001  addiu    $t0, $zero, 1
0200d4: 00004025  move     $t0, $zero
0200d8: 3c010006  lui      $at, 6
0200dc: 2421b23c  addiu    $at, $at, -0x4dc4   ; -> sub_06322c
0200e0: a208001d  sb       $t0, 0x1d($s0)
0200e4: 02202025  move     $a0, $s1
0200e8: 02402825  move     $a1, $s2
0200ec: 003e0821  addu     $at, $at, $fp
0200f0: 0020f809  jalr     $at
0200f4: 27a60008  addiu    $a2, $sp, 8
0200f8: 97a80008  lhu      $t0, 8($sp)
0200fc: 97ab000a  lhu      $t3, 0xa($sp)
020100: 00006825  move     $t5, $zero
020104: 00007025  move     $t6, $zero
020108: 00004825  move     $t1, $zero
02010c: 02285021  addu     $t2, $s1, $t0
020110: 01a06025  move     $t4, $t5
020114: 1000002b  b        0x201c4
020118: 00004025  move     $t0, $zero
02011c: 8d4f0000  lw       $t7, ($t2)
020120: afaf000c  sw       $t7, 0xc($sp)
020124: 960f0004  lhu      $t7, 4($s0)
020128: a7af0010  sh       $t7, 0x10($sp)
02012c: 954f0004  lhu      $t7, 4($t2)
020130: a7af0014  sh       $t7, 0x14($sp)
020134: 954f0006  lhu      $t7, 6($t2)
020138: 31ef0001  andi     $t7, $t7, 1
02013c: 15e0000e  bnez     $t7, 0x20178
020140: 298f0008  slti     $t7, $t4, 8
020144: 11e00019  beqz     $t7, 0x201ac
020148: 260f0048  addiu    $t7, $s0, 0x48
02014c: 27b8000c  addiu    $t8, $sp, 0xc
020150: 8f190000  lw       $t9, ($t8)
020154: 8f020004  lw       $v0, 4($t8)
020158: 01e87821  addu     $t7, $t7, $t0
02015c: adf90000  sw       $t9, ($t7)
020160: ade20004  sw       $v0, 4($t7)
020164: 8f190008  lw       $t9, 8($t8)
020168: 2508000c  addiu    $t0, $t0, 0xc
02016c: adf90008  sw       $t9, 8($t7)
020170: 1000000e  b        0x201ac
020174: 258c0001  addiu    $t4, $t4, 1
020178: 29af0008  slti     $t7, $t5, 8
02017c: 11e0000b  beqz     $t7, 0x201ac
020180: 260f00a8  addiu    $t7, $s0, 0xa8
020184: 27b8000c  addiu    $t8, $sp, 0xc
020188: 8f190000  lw       $t9, ($t8)
02018c: 8f020004  lw       $v0, 4($t8)
020190: 01e97821  addu     $t7, $t7, $t1
020194: adf90000  sw       $t9, ($t7)
020198: ade20004  sw       $v0, 4($t7)
02019c: 8f190008  lw       $t9, 8($t8)
0201a0: 25ad0001  addiu    $t5, $t5, 1
0201a4: 2529000c  addiu    $t1, $t1, 0xc
0201a8: adf90008  sw       $t9, 8($t7)
0201ac: 3c0f0000  lui      $t7, 0
0201b0: 01fc7821  addu     $t7, $t7, $gp
0201b4: 8def9f9c  lw       $t7, -0x6064($t7)
0201b8: 95ef0046  lhu      $t7, 0x46($t7)
0201bc: 25ce0001  addiu    $t6, $t6, 1
0201c0: 014f5021  addu     $t2, $t2, $t7
0201c4: 01cb782a  slt      $t7, $t6, $t3
0201c8: 55e0ffd5  bnel     $t7, $zero, 0x20120
0201cc: 8d4f0000  lw       $t7, ($t2)
0201d0: ae0c0040  sw       $t4, 0x40($s0)
0201d4: ae0d0044  sw       $t5, 0x44($s0)
0201d8: 8fbf0030  lw       $ra, 0x30($sp)
0201dc: 8fb40018  lw       $s4, 0x18($sp)
0201e0: 8fb3001c  lw       $s3, 0x1c($sp)
0201e4: 8fb20020  lw       $s2, 0x20($sp)
0201e8: 8fb10024  lw       $s1, 0x24($sp)
0201ec: 8fb00028  lw       $s0, 0x28($sp)
0201f0: 03e00008  jr       $ra
0201f4: 27bd0030  addiu    $sp, $sp, 0x30
0201f8: 3f000000  .word    0x3f000000

; ---- sub_06322c (leaf: S4 -> S10 / S12 record range)
06322c: 94a80012  lhu      $t0, 0x12($a1)
063230: a4c80000  sh       $t0, ($a2)
063234: 94880004  lhu      $t0, 4($a0)
063238: 11000005  beqz     $t0, 0x63250
06323c: 3c080000  lui      $t0, 0
063240: 011c4021  addu     $t0, $t0, $gp
063244: 8d089f9c  lw       $t0, -0x6064($t0)
063248: 10000005  b        0x63260
06324c: 95080030  lhu      $t0, 0x30($t0)
063250: 3c090000  lui      $t1, 0
063254: 013c4821  addu     $t1, $t1, $gp
063258: 8d299f9c  lw       $t1, -0x6064($t1)
06325c: 9528002e  lhu      $t0, 0x2e($t1)
063260: 3c090000  lui      $t1, 0
063264: 00a84021  addu     $t0, $a1, $t0
063268: 013c4821  addu     $t1, $t1, $gp
06326c: 94ca0000  lhu      $t2, ($a2)
063270: 95080012  lhu      $t0, 0x12($t0)
063274: 8d299f9c  lw       $t1, -0x6064($t1)
063278: 10000015  b        0x632d0
06327c: 95290046  lhu      $t1, 0x46($t1)
063280: 94a80014  lhu      $t0, 0x14($a1)
063284: a4c80000  sh       $t0, ($a2)
063288: 94880004  lhu      $t0, 4($a0)
06328c: 11000005  beqz     $t0, 0x632a4
063290: 3c080000  lui      $t0, 0
063294: 011c4021  addu     $t0, $t0, $gp
063298: 8d089f9c  lw       $t0, -0x6064($t0)
06329c: 10000005  b        0x632b4
0632a0: 95080030  lhu      $t0, 0x30($t0)
0632a4: 3c090000  lui      $t1, 0
0632a8: 013c4821  addu     $t1, $t1, $gp
0632ac: 8d299f9c  lw       $t1, -0x6064($t1)
0632b0: 9528002e  lhu      $t0, 0x2e($t1)
0632b4: 3c090000  lui      $t1, 0
0632b8: 013c4821  addu     $t1, $t1, $gp
0632bc: 8d299f9c  lw       $t1, -0x6064($t1)
0632c0: 00a84021  addu     $t0, $a1, $t0
0632c4: 94ca0000  lhu      $t2, ($a2)
0632c8: 95290048  lhu      $t1, 0x48($t1)
0632cc: 95080014  lhu      $t0, 0x14($t0)
0632d0: 010a4023  subu     $t0, $t0, $t2
0632d4: 0109001a  div      $zero, $t0, $t1
0632d8: 100000bf  b        0x635d8
0632dc: 00000000  nop      

; ... common tail: count = (next.ptr - this.ptr) / T[stride]
0635d8: 00004012  mflo     $t0
0635dc: a4c80002  sh       $t0, 2($a2)
0635e0: 00000000  nop      
0635e4: 03e00008  jr       $ra

; ---- sub_07b390 (leaf: return DB-REL)
07b390: 3c080000  lui      $t0, 0
07b394: 011c4021  addu     $t0, $t0, $gp
07b398: 8d089f9c  lw       $t0, -0x6064($t0)
07b39c: 03e00008  jr       $ra
07b3a0: 95020014  lhu      $v0, 0x14($t0)
