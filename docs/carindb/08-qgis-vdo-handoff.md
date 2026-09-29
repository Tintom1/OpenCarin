# Handoff: Ricerca su QGIS_VDO (CarinDB Reverse Engineering)

Questo documento riassume i risultati oggettivi emersi dall'analisi del repository pubblico **`QGIS_VDO`** di *lugovskovp* e della relativa serie di articoli su Habr, ai fini di supportare un futuro agente nello sviluppo di strumenti compatibili col formato CarinDB (BMW MK4 / VDO Dayton).

## 1. Risorse Pubbliche Identificate
*   **Repository GitHub:** [lugovskovp/QGIS_VDO](https://github.com/lugovskovp/QGIS_VDO) (Plugin per QGIS scritto in Python).
*   **Articoli su Habr:** Serie in 5 parti (Part 0-4) sul reverse engineering del formato VDO Dayton / Carindb, inclusa la logica di Tesseract e decodifica spaziale.
*   **Cartella `research/`:** Il repository contiene una vasta suite di script Python dedicati all'analisi bruta degli alberi di Huffman e algoritmi di delta-coding BMW.

## 2. Architettura del Codice
*   L'implementazione Python usa un approccio OOP (`vdo/blocks/`): ogni blocco è mappato su una specifica classe derivata da `block_base.py` (es. `block_0x07`, `block_0x0A`).
*   Include un modulo `datatypes.py` per le primitive di base (`BLADDR`, `LIST`, `COORD`) e `bitstream.py` per il parsing a livello di bit.

## 3. Scoperte Oggettive sui Tipi di Blocco (Block ID)

Di seguito, i dati estratti strettamente dal codice sorgente dell'autore (senza deduzioni esterne).

### Blocco `0x09` (Spatial Index / Folder Maps)
*   **Implementazione:** File `block_0x09.py`.
*   **Struttura scoperta:** È rappresentato come una griglia 2D piatta (matrice geografica).
*   **Logica matematica usata nel codice:**
    *   `qty_x = (max_lon - origin_lon) // item_side`
    *   `qty_y = (max_lat - origin_lat) // item_side`
*   **Codifica:** La griglia è formata da puntatori di 2 byte (`_STRUCT_SHORT`) che puntano a una tabella di `BLADDR` (indirizzi blocco a 4 byte).
*   **Decodifica spaziale (RLE):** L'autore usa esplicitamente un ciclo di *Run-Length Encoding (RLE)* per l'asse X e l'asse Y per calcolare le dimensioni effettive della singola tile (`size_X`, `size_Y`), unendo celle adiacenti che contengono lo stesso puntatore.

### Blocco `0x0A` (Country Info)
*   **Implementazione:** File `block_0x0A.py`.
*   **Offset 28 (`+0x1C`):** Il codice definisce e impone via `struct.unpack(">LL")` due costanti `DWORD` esatte: `0x01f4012c` (decimale: 32768300, pari a `500, 300` in short) e `0x03e801f4` (decimale: 65536500, pari a `1000, 500` in short). Non gli viene attribuito alcun significato semantico nel codice ("вообще это константы" / "sono solo costanti").
*   **Offset 36 (`+0x24`):** Legge un `ushort`. Se il valore è `1`, attiva una property chiamata `is_island`.

### Blocchi `0x0B`, `0x0D`, `0x0F`, `0x11` (Indici / Tries)
*   **Implementazione:** File `block_0x0B.py` e template C in `NOTES.md`.
*   **Struttura scoperta:** L'autore dichiara che tutti e 4 questi blocchi (Paesi, Città, Strade, POI) condividono esattamente la **medesima struct di base**, denominata `BT_0x0B_0x0D_0x0F_0x11`.
*   **Formato del Record (`CH_IDX`):** È un nodo di un Trie di 12 byte (`3 * DWORD`):
    1.  `BL_ADDR` (4 byte).
    2.  `char` (1 byte, la singola lettera/carattere).
    3.  `is_ptr_out` (1 byte). Questo è un flag booleano. Il codice lo verifica controllando il tipo del target di `bl_postaddr` (se è del livello inferiore, il link "esce", altrimenti è un link "interno" all'albero).
    4.  `LIST` (4 byte per puntatore e counter).
    5.  `align` (2 byte, padding o costanti 0).

### Blocco `0x13` (CD Info / Bibliografia)
*   **Implementazione:** File `block_0x13.py`.
*   **Compressione:** Se l'header del blocco ha il flag `is_compressed` attivato (zlib), il codice dell'autore interrompe immediatamente l'analisi (`break;`) senza decomprimerlo.

### Blocchi `0x17`, `0x18`, `0x19`, `0x1A`, `0x1B` (TMC / Location Tables)
*   **Riscontro nel codice:** I parser per questi specifici block type sono del tutto assenti nella cartella `blocks/`.
*   L'enumeratore in `enums.py` salta questi ID o li associa a concetti differenti (es. `0x17` = `Slovene` come lingua o `Bank` come categoria POI).
*   I valori testuali `0x17` e `0x19` appaiono unicamente negli script di ricerca (`bmw huff м3 5.py`), dove l'autore li annota come "token escape ad alta frequenza" per l'albero di Huffman. Non c'è alcun collegamento al TMC o all'indice di posizione mappa.
