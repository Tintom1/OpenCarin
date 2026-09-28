"""Constants for CF=1 Codec."""

SECTOR = 512
HDR = 8

# --- indici nella RECORD_SIZE_TABLE usati dal decoder del tipo 0x00 ----------
T_DESC_BASE = 0x05      # offset del SECTION_DESCRIPTOR nel blocco (8)
T_REC_S6 = 0x06         # record sezione 6
T_REC_S4 = 0x08         # record sezione 4
T_TAIL_S4 = 0x09        # offset dei campi di coda nel record della sezione 4
T_PROLOG = 0x0B         # lunghezza del prologo in chiaro del tipo 0x00
T_REC_S7 = 0x0C         # record sezione 7
T_REC_S9 = 0x0F         # record sezione 9   (copiata verbatim)
T_REC_S5 = 0x10         # record sezione 5
T_REC_S3 = 0x12         # record sezione 3   (copiata verbatim, +1 record)
T_REC_S11 = 0x13        # record sezione 11
T_REC_S10 = 0x14        # record sezione 10  (copiata verbatim)
T_REC_S12 = 0x15        # record sezione 12  (copiata verbatim)
T_REC_S0 = 0x40         # record sezioni 0,1,2
T_REC_S13 = 0x4C        # record sezione 13 (DB-REL >= 21)
T_REC_S14 = 0x59        # record sezione 14 (DB-REL >= 23), indice dei nomi

# --- indici RECORD_SIZE_TABLE specifici di BLOCK_TYPE 0x0E -------------------
T_PROLOG_0E = 0x2B      # lunghezza del prologo (48 = 0x30)
T_REC_S0_0E = 0x2D      # record sezione 0 (8 byte: ">HBBHH")
T_REC_S1_0E = 0x41      # record sezione 1 (6 byte)
T_REC_S2_0E = 0x42      # record sezione 2 (24 byte; metà ancora grezza, metà delta)

# --- indici RECORD_SIZE_TABLE dei BLOCK_TYPE 0x14-0x16, 0x1C-0x1E ------------
# Fonte: RR db_pub sub_004b88 (bsw2 0101), T[id] = lhu (L + 0x1e + 2*id), L = gp[-0x7f24].
# Stessi indici in m68k pbp+0x46aa, T[idx] -> -(0x71cc-2*idx)(a6).
T_PROLOG_141516 = 0x3D  # lunghezza prologo            RR +0x4bac (L+0x98)
T_REC_S1_141516 = 0x3A  # sezione 1                    RR +0x4c7c (L+0x92)
T_REC_S0_141516 = 0x3B  # sezione 0                    RR +0x4c44 (L+0x94)
T_REC_S2_141516 = 0x3C  # sezione 2                    RR +0x4cb8 (L+0x96)
T_S3_DISP_141516 = 0x3F # selettore sez.3 a desc+T[0x3f]+0x10  RR +0x4cf4 (L+0x9c)
T_REC_E4_141516 = 0x15  # sezione 4 (passata DB-REL>=20)  RR +0x4e48 (L+0x48)
T_REC_E5_141516 = 0x59  # sezione 5 (passata DB-REL>=23)  RR +0x4f18 (L+0xd0)


# tabella dei caratteri del decoder di testo (pbp IData, offset dati 0x1450)
CHARMAP = bytes.fromhex(
    "61657374720020646768696c6e6f"
    "e0e1e2e3e4e5e7e8e9eaebecedeeeff1f2f3f4f5f6f8f9fafbfcfdac"
)


