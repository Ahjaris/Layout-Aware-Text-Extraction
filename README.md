# Layout Aware Text Extraction

Pipeline ekstraksi teks berbasis layout yang mampu membaca teks dari gambar, mempertahankan posisi teks, memperkirakan gaya visual seperti ukuran font, warna teks, warna background, alignment, dan ketebalan font, lalu menghasilkan output HTML interaktif yang dapat diedit kembali melalui browser.

## Daftar Isi

- [Gambaran Umum](#gambaran-umum)
- [Kemampuan Utama](#kemampuan-utama)
- [Arsitektur Pipeline](#arsitektur-pipeline)
- [Tech Stack](#tech-stack)
- [Struktur Project](#struktur-project)
- [Prasyarat](#prasyarat)
- [Instalasi](#instalasi)
- [Konfigurasi](#konfigurasi)
- [Menjalankan Pipeline](#menjalankan-pipeline)
- [Parameter CLI](#parameter-cli)
- [Output Project](#output-project)
- [Format JSON Metadata](#format-json-metadata)
- [Alur Kerja Program](#alur-kerja-program)
- [Penjelasan Modul Kode](#penjelasan-modul-kode)
- [Keputusan Desain](#keputusan-desain)
- [Catatan Pengembangan](#catatan-pengembangan)

---

## Gambaran Umum

Project ini dibuat untuk melakukan **layout-aware text extraction** dari gambar. Sistem tidak hanya membaca teks menggunakan OCR, tetapi juga mencoba mempertahankan informasi visual dari gambar asli.

Informasi visual yang dipertahankan antara lain:

- isi teks,
- posisi teks pada gambar,
- ukuran area teks,
- confidence hasil OCR,
- ukuran font hasil estimasi,
- warna teks,
- warna background di sekitar teks,
- alignment teks,
- dan ketebalan font.

Hasil utama dari pipeline ini adalah file HTML interaktif. Pada file HTML tersebut, gambar digunakan sebagai background, lalu teks hasil OCR diletakkan kembali sesuai posisi yang terdeteksi. Setiap teks bersifat `contenteditable`, sehingga pengguna dapat mengeditnya langsung melalui browser.

Selain HTML, pipeline juga menghasilkan file JSON metadata yang menyimpan data detail dari setiap teks hasil OCR. JSON ini berguna untuk debugging, analisis hasil ekstraksi, atau pengembangan output lanjutan seperti export ke PowerPoint, PDF, atau editor visual.

---

## Kemampuan Utama

Kemampuan utama dari project ini:

- Membaca gambar dari folder input atau dari satu file gambar.
- Mendukung format gambar `.jpg`, `.jpeg`, `.png`, `.bmp`, dan `.webp`.
- Melakukan preprocessing gambar sebelum OCR.
- Melakukan peningkatan kontras menggunakan CLAHE.
- Mendukung OCR menggunakan PaddleOCR dan EasyOCR.
- Menggunakan EasyOCR sebagai fallback jika PaddleOCR gagal.
- Melakukan koreksi teks hasil OCR.
- Menghapus noise seperti teks logo atau teks dengan kualitas rendah.
- Menggabungkan teks yang berada pada satu baris.
- Menghapus duplikasi hasil OCR.
- Mengestimasi ukuran font berdasarkan bounding box.
- Mengestimasi warna teks menggunakan clustering warna.
- Mengestimasi warna background untuk cover teks asli.
- Mengestimasi alignment teks.
- Mengestimasi ketebalan font.
- Menghasilkan HTML interaktif yang dapat diedit.
- Menghasilkan JSON metadata untuk setiap gambar.
- Menghasilkan file debug berupa bounding box dan mask jika mode debug aktif.

---

## Arsitektur Pipeline

```text
┌──────────────────────────────────────────────────────────────┐
│                        INPUT IMAGE                           │
│                                                              │
│  Gambar dari folder input/ atau satu file gambar             │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                    IMAGE PREPROCESSING                       │
│                                                              │
│  - Resize / upscale jika gambar terlalu kecil                │
│  - Konversi BGR ke HSV                                       │
│  - Peningkatan kontras menggunakan CLAHE                     │
│  - Simpan gambar sementara ke output/_tmp/                   │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                         OCR ENGINE                           │
│                                                              │
│  PaddleOCR / EasyOCR                                         │
│  - Deteksi bounding box teks                                 │
│  - Ekstraksi isi teks                                        │
│  - Confidence score                                          │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                    TEXT CORRECTION                           │
│                                                              │
│  - Normalisasi whitespace                                    │
│  - Perbaikan spasi antar kata                                │
│  - Koreksi kata yang sering salah hasil OCR                  │
│  - Replacement berbasis pola                                 │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                  FILTER, DEDUPLICATE, MERGE                  │
│                                                              │
│  - Filter teks kosong / noise                                │
│  - Filter area logo kanan atas                               │
│  - Filter kontras rendah                                     │
│  - Hapus teks duplikat                                       │
│  - Gabungkan teks dalam satu baris                           │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                      STYLE ESTIMATION                        │
│                                                              │
│  - Estimasi font size                                        │
│  - Estimasi font weight                                      │
│  - Estimasi warna teks                                       │
│  - Estimasi warna cover background                           │
│  - Estimasi alignment                                        │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                    BACKGROUND PROCESSING                     │
│                                                              │
│  Mode CSS:                                                   │
│  - Gambar asli digunakan sebagai background                  │
│  - Teks asli ditutup dengan elemen cover CSS                 │
│                                                              │
│  Mode Inpaint:                                               │
│  - Mask teks dibuat dari elemen OCR                          │
│  - Teks asli dihapus menggunakan OpenCV inpainting           │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                         OUTPUT                               │
│                                                              │
│  - HTML interaktif                                           │
│  - JSON metadata                                             │
│  - Background image                                          │
│  - Results summary                                           │
│  - Debug image dan mask jika debug aktif                     │
└──────────────────────────────────────────────────────────────┘

Tech Stack
Komponen	Teknologi	Keterangan
Bahasa Pemrograman	Python	Bahasa utama pipeline
OCR Engine Utama	PaddleOCR	Digunakan secara default untuk ekstraksi teks
OCR Fallback	EasyOCR	Digunakan jika PaddleOCR gagal atau dipilih manual
Image Processing	OpenCV	Preprocessing, mask, inpainting, color detection
Numerical Processing	NumPy	Operasi array, perhitungan style, dan clustering warna
Output Editor	HTML, CSS, JavaScript	Menampilkan hasil ekstraksi dalam bentuk editor interaktif
Data Output	JSON	Menyimpan metadata hasil ekstraksi teks
CLI	argparse	Menjalankan pipeline melalui terminal
Struktur Project
layout-aware-text-extraction/
├── input/
│   └── ekosistem.jpg
│
├── output/
│   ├── _tmp/
│   │   └── ekosistem_ocr_input.png
│   │
│   ├── ekosistem_background.png
│   ├── ekosistem_css_cover.html
│   ├── ekosistem_data.json
│   ├── ekosistem_debug.png
│   ├── ekosistem_mask.png
│   └── results.json
│
├── sul/
│   ├── Include/
│   ├── Lib/
│   ├── Scripts/
│   ├── share/
│   └── pyvenv.cfg
│
├── .gitignore
├── pipeline.py
└── requirements.txt

Keterangan:

File / Folder	Keterangan
input/	Folder untuk menyimpan gambar yang akan diproses
output/	Folder hasil keluaran pipeline
output/_tmp/	Folder sementara untuk menyimpan gambar hasil preprocessing sebelum OCR
*_background.png	Background yang digunakan pada file HTML
*_css_cover.html	Output utama berupa HTML interaktif
*_data.json	Metadata detail hasil ekstraksi teks dari satu gambar
*_debug.png	Gambar debug berisi bounding box teks
*_mask.png	Mask area teks yang terdeteksi
results.json	Ringkasan output dari seluruh gambar yang diproses
sul/	Virtual environment Python
pipeline.py	File utama pipeline
requirements.txt	Daftar dependency Python
.gitignore	File untuk mengecualikan folder/file tertentu dari Git
Prasyarat

Sebelum menjalankan project, pastikan sudah tersedia:

Python 3.10 atau lebih baru
pip
Virtual environment Python
OpenCV
NumPy
PaddleOCR atau EasyOCR

Project ini dapat dijalankan di Windows, Linux, maupun MacOS. Untuk Windows, disarankan menggunakan PowerShell atau terminal Visual Studio Code.

Instalasi
1. Clone repository
git clone https://github.com/username/layout-aware-text-extraction.git
cd layout-aware-text-extraction
2. Buat virtual environment
python -m venv sul
3. Aktifkan virtual environment

Windows:

sul\Scripts\activate

Mac/Linux:

source sul/bin/activate
4. Install dependency
pip install -r requirements.txt

Contoh isi requirements.txt:

opencv-python
numpy
easyocr
paddleocr
paddlepaddle

Jika hanya ingin menggunakan EasyOCR, dependency PaddleOCR dapat disesuaikan.

Konfigurasi

Konfigurasi utama berada di bagian konstanta pada awal file pipeline.py.

MIN_CONF = 0.38
UPSCALE_IF_WIDTH_BELOW = 1600
OCR_UPSCALE = 2.0
FONT_FAMILY = '"Poppins","Montserrat","Trebuchet MS","Arial",sans-serif'
LINE_HEIGHT = 1.12
MIN_FONT_SIZE = 10
MAX_FONT_SIZE = 90

Keterangan:

Konstanta	Fungsi
MIN_CONF	Confidence minimum agar hasil OCR diterima
UPSCALE_IF_WIDTH_BELOW	Batas lebar gambar untuk dilakukan upscale
OCR_UPSCALE	Skala pembesaran gambar sebelum OCR
FONT_FAMILY	Font default pada output HTML
LINE_HEIGHT	Tinggi baris teks
MIN_FONT_SIZE	Ukuran font minimum
MAX_FONT_SIZE	Ukuran font maksimum untuk teks biasa

Konfigurasi area logo kanan atas:

IGNORE_TOP_RIGHT_LOGO = True
LOGO_X_START_RATIO = 0.78
LOGO_Y_END_RATIO = 0.18
MIN_LOCAL_CONTRAST = 18.0

Keterangan:

Konstanta	Fungsi
IGNORE_TOP_RIGHT_LOGO	Mengaktifkan filter area logo kanan atas
LOGO_X_START_RATIO	Batas awal area logo berdasarkan rasio lebar gambar
LOGO_Y_END_RATIO	Batas akhir area logo berdasarkan rasio tinggi gambar
MIN_LOCAL_CONTRAST	Kontras minimum agar teks tidak dianggap noise
Menjalankan Pipeline
1. Menjalankan dengan input folder default

Masukkan gambar ke folder input/, lalu jalankan:

python pipeline.py

Secara default, program membaca gambar dari:

./input

dan menyimpan hasil ke:

./output
2. Menjalankan dengan engine PaddleOCR
python pipeline.py --engine paddle

PaddleOCR adalah engine default.

3. Menjalankan dengan engine EasyOCR
python pipeline.py --engine easyocr
4. Menjalankan dengan mode debug
python pipeline.py --debug

Mode debug akan menghasilkan file tambahan:

output/nama_gambar_debug.png
output/nama_gambar_mask.png
5. Membersihkan folder output sebelum proses
python pipeline.py --clean-output

Perintah ini akan menghapus folder output/ lama, lalu membuat output baru dari awal.

6. Menggunakan mode CSS cover
python pipeline.py --cover-mode css

Mode ini adalah mode default. Pada mode ini, gambar asli digunakan sebagai background, lalu teks asli ditutup menggunakan elemen cover CSS.

7. Menggunakan mode inpaint
python pipeline.py --cover-mode inpaint

Mode ini mencoba menghapus teks asli dari gambar menggunakan OpenCV inpainting.

8. Menjalankan dengan parameter lengkap
python pipeline.py --input ./input --output ./output --engine paddle --debug --clean-output --cover-mode css
Parameter CLI
Parameter	Default	Pilihan	Keterangan
--input	./input	path file/folder	Lokasi gambar input
--output	./output	path folder	Lokasi penyimpanan output
--engine	paddle	paddle, easyocr	OCR engine yang digunakan
--debug	False	-	Menyimpan debug image dan mask
--clean-output	False	-	Menghapus folder output sebelum proses
--cover-mode	css	css, inpaint	Mode pembuatan background
Output Project

Setelah pipeline dijalankan, hasil akan disimpan di folder output/.

Contoh output untuk gambar ekosistem.jpg:

output/
├── _tmp/
│   └── ekosistem_ocr_input.png
│
├── ekosistem_background.png
├── ekosistem_css_cover.html
├── ekosistem_data.json
├── ekosistem_debug.png
├── ekosistem_mask.png
└── results.json

Keterangan output:

File / Folder	Fungsi
ekosistem_background.png	Background yang digunakan dalam file HTML
ekosistem_css_cover.html	Output utama berupa HTML interaktif
ekosistem_data.json	Metadata detail semua teks hasil OCR pada gambar tersebut
ekosistem_debug.png	Visualisasi bounding box teks, muncul jika --debug aktif
ekosistem_mask.png	Mask area teks, muncul jika --debug aktif
results.json	Ringkasan lokasi file output dari semua gambar
_tmp/	Folder sementara untuk file gambar preprocessing sebelum OCR

Folder _tmp bukan output final. Folder ini digunakan untuk menyimpan gambar sementara hasil preprocessing, misalnya gambar yang sudah di-upscale atau ditingkatkan kontrasnya sebelum dibaca oleh OCR. Setelah proses selesai, folder _tmp boleh dihapus jika tidak diperlukan untuk debugging.

Format JSON Metadata

Setiap gambar menghasilkan file JSON metadata dengan nama:

nama_gambar_data.json

Contoh struktur JSON:

{
  "image": "ekosistem.jpg",
  "width": 5734,
  "height": 3200,
  "elements": [
    {
      "text": "Ekosistem Inovasi Terintegrasi",
      "x": 316,
      "y": 259,
      "w": 2898,
      "h": 188,
      "confidence": 0.971,
      "font_size": 200,
      "line_height": 1.12,
      "font_weight": "700",
      "color": "#24669f",
      "cover_color": "#ffffff",
      "align": "left",
      "bg_lum": 255.0
    }
  ]
}

Keterangan field utama:

Field	Keterangan
image	Nama file gambar yang diproses
width	Lebar gambar dalam pixel
height	Tinggi gambar dalam pixel
elements	Daftar teks yang berhasil diekstrak

Keterangan field di dalam elements:

Field	Keterangan
text	Isi teks hasil OCR
x	Posisi teks dari sisi kiri gambar
y	Posisi teks dari sisi atas gambar
w	Lebar bounding box teks
h	Tinggi bounding box teks
confidence	Tingkat keyakinan hasil OCR
font_size	Ukuran font hasil estimasi
line_height	Tinggi baris teks
font_weight	Ketebalan font
color	Warna teks hasil estimasi dalam format HEX
cover_color	Warna background untuk menutup teks asli
align	Alignment teks
bg_lum	Tingkat kecerahan background

JSON metadata digunakan untuk:

Debugging hasil OCR
Pengguna dapat mengecek apakah teks, posisi, warna, dan ukuran font sudah sesuai.
Menyimpan hasil ekstraksi secara terstruktur
Hasil OCR tidak hanya tersimpan di HTML, tetapi juga tersedia dalam bentuk data.
Membandingkan hasil eksperimen
Misalnya membandingkan hasil sebelum dan sesudah mengubah rumus font size atau parameter filter.
Sumber data untuk pengembangan lanjutan
JSON dapat digunakan untuk membuat export ke PowerPoint, PDF, editor canvas, atau sistem layout reconstruction lainnya.

Selain nama_gambar_data.json, program juga menghasilkan:

results.json

File ini berisi ringkasan path output dari semua gambar yang berhasil diproses.

Alur Kerja Program
1. Membaca Input

Program membaca input dari argumen:

--input

Jika input berupa satu file gambar, hanya file tersebut yang diproses. Jika input berupa folder, program akan memproses semua gambar dengan ekstensi:

.jpg, .jpeg, .png, .bmp, .webp
2. Preprocessing Gambar

Fungsi utama:

preprocess_for_ocr(img)

Tahapan preprocessing:

Membaca ukuran gambar.
Jika lebar gambar lebih kecil dari UPSCALE_IF_WIDTH_BELOW, gambar diperbesar.
Gambar dikonversi dari BGR ke HSV.
CLAHE diterapkan pada channel V atau brightness.
Gambar dikonversi kembali dari HSV ke BGR.
Gambar hasil preprocessing disimpan sementara ke folder _tmp.

Tujuan preprocessing adalah meningkatkan kualitas gambar sebelum OCR, terutama pada gambar yang memiliki kontras rendah atau resolusi kecil.

3. Menjalankan OCR

Fungsi utama:

run_ocr(img, out_dir, stem, engine)

Pipeline mendukung dua OCR engine:

PaddleOCR
EasyOCR

Jika engine yang dipilih adalah easyocr, program langsung menjalankan EasyOCR.

Jika engine yang dipilih adalah paddle, program mencoba menjalankan PaddleOCR terlebih dahulu. Jika PaddleOCR gagal, program akan otomatis fallback ke EasyOCR.

Output awal OCR berbentuk data:

{
  "text": "Contoh Teks",
  "x": 120,
  "y": 80,
  "w": 300,
  "h": 45,
  "confidence": 0.95
}
4. Koreksi Teks OCR

Fungsi utama:

correct_text(text)

Tahapan koreksi teks:

Menghapus spasi berlebih.
Mengganti dash panjang menjadi dash biasa.
Memperbaiki spasi antara huruf kecil dan huruf besar.
Memperbaiki spasi antara angka dan huruf.
Menghapus spasi yang salah di sekitar tanda baca.
Mengganti kata yang sering salah terbaca oleh OCR.
Menggunakan pola replacement untuk teks tertentu.

Contoh koreksi:

Cehter  → Center
Researc → Research
Resourc → Resource
profie  → profile
Imoge   → Image
Studic  → Studio
5. Filter Noise

Fungsi utama:

filter_noise(img, elements)

Tahap ini menghapus elemen teks yang dianggap noise.

Elemen dapat dihapus jika:

teks kosong,
kualitas teks rendah,
berada di area logo kanan atas,
bounding box terlalu kecil,
kontras lokal rendah dan confidence OCR rendah.

Tujuan tahap ini adalah mengurangi teks palsu, artefak, atau elemen visual yang salah terbaca sebagai teks.

6. Deduplication

Fungsi utama:

deduplicate(elements)

Tahap ini menghapus elemen OCR yang terdeteksi ganda.

Duplikasi dideteksi berdasarkan:

Intersection over Union atau IoU antar bounding box,
teks yang sama dengan posisi vertikal yang berdekatan.

Jika ada dua elemen yang dianggap sama, program mempertahankan elemen dengan confidence atau area yang lebih baik.

7. Merge Same Line

Fungsi utama:

merge_same_line(elements, img_w)

OCR sering memecah satu baris menjadi beberapa bagian. Fungsi ini menggabungkan elemen-elemen yang berada pada baris yang sama.

Pertimbangan merge:

overlap vertikal,
jarak horizontal antar elemen,
tinggi rata-rata teks,
urutan posisi kiri ke kanan.

Hasil akhirnya adalah satu elemen teks gabungan dengan bounding box baru.

8. Estimasi Style

Fungsi utama:

enrich_style(img, elements)

Fungsi ini menambahkan informasi style visual ke setiap elemen teks.

Style yang ditambahkan:

font_size,
line_height,
font_weight,
color,
cover_color,
align,
bg_lum.

Contoh hasil:

{
  "text": "Services",
  "x": 3565,
  "y": 2240,
  "w": 462,
  "h": 138,
  "confidence": 0.998,
  "font_size": 90,
  "line_height": 1.12,
  "font_weight": "700",
  "color": "#cae4ea",
  "cover_color": "#013161",
  "align": "center",
  "bg_lum": 40.12
}
9. Estimasi Ukuran Font

Fungsi utama:

estimate_font_size(el, img_w, img_h)

Ukuran font ditentukan berdasarkan tinggi bounding box dan jenis elemen teks.

Kategori teks:

Hero title
Judul besar yang biasanya berada di area tengah gambar.
Top title
Judul yang berada di area atas gambar.
Teks biasa
Teks selain judul.

Untuk judul besar, ukuran font dihitung lebih besar agar mendekati tampilan asli. Untuk top title, teks dibuat uppercase dan ukuran font diperbesar dari tinggi bounding box. Untuk teks biasa, ukuran font mengikuti tinggi bounding box dengan batas minimum dan maksimum.

10. Estimasi Font Weight

Fungsi utama:

estimate_weight(el, bg_lum, img_w, img_h)

Fungsi ini menentukan ketebalan font.

Jika teks merupakan hero title atau top title, maka font dibuat tebal:

font_weight = 700

Kode juga memiliki daftar heavy_keywords:

heavy_keywords = [
    'talent development', 'cyber security', 'cloud computing',
    'research center', 'human resource', 'services',
]

Jika teks mengandung salah satu keyword tersebut, maka teks dianggap penting dan diberi font_weight = 700.

Contohnya, teks Services pada JSON metadata memiliki nilai:

"font_weight": "700"

Artinya teks tersebut akan ditampilkan lebih tebal di HTML.

11. Estimasi Warna Teks

Fungsi utama:

estimate_text_color(crop, mask, el, img_h)

Warna teks diperkirakan menggunakan K-Means clustering dengan k=2.

Alurnya:

Area teks di-crop dari gambar.
Pixel di dalam crop dikumpulkan.
K-Means membagi pixel menjadi dua cluster warna.
Cluster dengan jumlah pixel lebih sedikit diasumsikan sebagai warna teks.
Warna BGR dikonversi menjadi HEX.

Contoh:

"color": "#24669f"
12. Estimasi Warna Cover Background

Fungsi utama:

estimate_cover_color(crop)

Warna cover background diestimasi dari border area crop. Program mengambil warna median dari bagian pinggir crop, lalu menggunakannya sebagai warna penutup teks asli.

Contoh:

"cover_color": "#ffffff"

Warna ini digunakan pada elemen cover di HTML.

13. Mask dan Inpainting

Fungsi utama:

build_mask(img, elements)
inpaint_background(img, mask)

Jika menggunakan mode inpaint, program akan:

Membuat mask area teks berdasarkan elemen OCR.
Memperlebar area mask menggunakan dilasi.
Menghapus teks asli menggunakan OpenCV inpainting TELEA.
Menyimpan hasilnya sebagai background baru.

Jika menggunakan mode css, gambar asli tetap digunakan sebagai background dan teks asli ditutup menggunakan elemen CSS cover.

14. Generate HTML

Fungsi utama:

generate_html(elements, img_w, img_h, bg_img, html_path, title)

Fungsi ini menghasilkan HTML final yang terdiri dari:

canvas slide,
background image,
elemen cover untuk menutup teks asli,
elemen teks hasil OCR,
CSS styling,
toolbar editor,
JavaScript untuk interaksi editing.

Setiap teks dibuat sebagai elemen:

<div class="text-el" contenteditable="true">
  Contoh Teks
</div>

Karena menggunakan contenteditable, teks dapat diedit langsung melalui browser.

Fitur Editor HTML

Output HTML memiliki toolbar floating seperti editor sederhana. Toolbar akan muncul ketika pengguna mengklik teks.

Fitur toolbar:

memilih font family,
memperbesar ukuran font,
memperkecil ukuran font,
bold,
italic,
underline,
strikethrough,
mengubah warna teks,
align left,
align center,
align right,
justify.

Toolbar ini membantu pengguna memperbaiki hasil OCR secara manual tanpa perlu mengubah kode Python.

Penjelasan Modul Kode
1. Konstanta Konfigurasi

Mengatur parameter global pipeline, seperti confidence OCR, ukuran font, font family, dan filter logo.

Contoh:

MIN_CONF = 0.38
OCR_UPSCALE = 2.0
FONT_FAMILY = '"Poppins","Montserrat","Trebuchet MS","Arial",sans-serif'
2. Utilitas Umum

Berisi fungsi bantu:

Fungsi	Keterangan
safe_int()	Membulatkan nilai menjadi integer
clamp()	Membatasi nilai agar tetap dalam range
bgr_to_hex()	Mengubah warna BGR menjadi HEX
hex_to_rgb()	Mengubah warna HEX menjadi RGB
luminance_bgr()	Menghitung luminance warna
NumpyEncoder	Mengubah tipe NumPy agar dapat disimpan ke JSON
3. Koreksi dan Normalisasi Teks

Berisi fungsi untuk membersihkan teks hasil OCR.

Fungsi	Keterangan
norm_text()	Normalisasi whitespace dan dash
fix_spacing()	Memperbaiki spasi antar karakter
correct_text()	Koreksi teks hasil OCR
text_quality_score()	Menghitung kualitas teks
4. Preprocessing dan OCR

Berisi fungsi untuk mempersiapkan gambar dan menjalankan OCR.

Fungsi	Keterangan
preprocess_for_ocr()	Melakukan upscale dan CLAHE
run_paddleocr()	Menjalankan PaddleOCR
run_easyocr()	Menjalankan EasyOCR
run_ocr()	Memilih OCR engine dan fallback
5. Analisis Visual Elemen Teks

Berisi fungsi untuk menganalisis area teks.

Fungsi	Keterangan
expand_box()	Memperluas bounding box
estimate_bg_color()	Estimasi warna background
local_contrast()	Menghitung kontras lokal
text_mask_from_crop()	Membuat mask teks dari crop
6. Klasifikasi Elemen Teks

Berisi fungsi untuk menentukan jenis teks.

Fungsi	Keterangan
is_top_title_area()	Mendeteksi judul bagian atas
is_hero_title()	Mendeteksi judul besar di tengah
is_in_logo_region()	Mendeteksi teks di area logo kanan atas
7. Estimasi Gaya

Berisi fungsi untuk menentukan style visual teks.

Fungsi	Keterangan
estimate_text_color()	Estimasi warna teks
estimate_cover_color()	Estimasi warna background cover
estimate_font_size()	Estimasi ukuran font
estimate_weight()	Estimasi ketebalan font
estimate_align()	Estimasi alignment teks
enrich_style()	Menambahkan semua style ke elemen teks
8. Filter, Deduplication, dan Merge

Berisi fungsi untuk membersihkan dan menggabungkan hasil OCR.

Fungsi	Keterangan
filter_noise()	Menghapus elemen noise
iou()	Menghitung Intersection over Union
vertical_overlap_ratio()	Menghitung overlap vertikal
deduplicate()	Menghapus elemen duplikat
merge_same_line()	Menggabungkan teks satu baris
9. Background Processing

Berisi fungsi untuk membuat mask dan menghapus teks asli jika mode inpaint digunakan.

Fungsi	Keterangan
build_mask()	Membuat mask teks
inpaint_background()	Menghapus teks menggunakan OpenCV inpainting
10. HTML Generator

Berisi fungsi untuk menghasilkan file HTML final.

Fungsi	Keterangan
rel_path()	Membuat relative path untuk background
generate_html()	Membuat HTML interaktif
11. Debug dan Output

Berisi fungsi untuk menyimpan gambar debug.

Fungsi	Keterangan
save_debug()	Menyimpan gambar dengan bounding box teks
12. Pipeline Utama

Fungsi utama:

process_image(path, out_dir, engine, debug, cover_mode)

Urutan proses:

Membaca gambar.
Membuat folder temporary _tmp.
Menjalankan OCR.
Memfilter noise.
Menggabungkan teks pada baris yang sama.
Menambahkan informasi style.
Membuat background.
Membuat HTML.
Membuat JSON metadata.
Menyimpan debug output jika mode debug aktif.
Mengembalikan path hasil output.
13. Entry Point

Fungsi utama program:

main()

Bagian ini mengatur:

argument CLI,
input path,
output path,
pemilihan OCR engine,
mode debug,
mode cover,
dan pemrosesan semua gambar.
Keputusan Desain
1. OCR Engine dengan Fallback

PaddleOCR digunakan sebagai engine utama karena memiliki kemampuan deteksi teks dan bounding box yang baik. Namun, jika PaddleOCR gagal, sistem otomatis menggunakan EasyOCR. Pendekatan ini membuat pipeline lebih fleksibel dan tidak langsung berhenti ketika salah satu OCR engine bermasalah.

2. Preprocessing dengan CLAHE

CLAHE digunakan untuk meningkatkan kontras gambar sebelum OCR. Teknik ini diterapkan pada channel brightness dari ruang warna HSV. Tujuannya adalah membuat teks lebih jelas dan lebih mudah dibaca oleh OCR.

3. CSS Cover sebagai Mode Default

Mode css dipilih sebagai default karena lebih aman dalam mempertahankan tampilan gambar asli. Pada mode ini, gambar asli tetap digunakan sebagai background, sementara area teks asli ditutup dengan elemen cover yang warnanya diestimasi dari background sekitar teks.

Mode ini lebih ringan dan lebih mudah dikoreksi manual dibandingkan inpainting.

4. Inpainting sebagai Mode Alternatif

Mode inpaint disediakan untuk menghapus teks asli dari gambar. Mode ini cocok jika pengguna ingin background yang lebih bersih. Namun, hasil inpainting dapat kurang stabil pada background kompleks, sehingga mode ini tidak dijadikan default.

5. Estimasi Font Berdasarkan Bounding Box

OCR tidak memberikan informasi font asli. Oleh karena itu, ukuran font diperkirakan dari tinggi dan lebar bounding box. Untuk judul besar, perhitungan dibuat lebih agresif agar hasil HTML mendekati ukuran judul pada gambar asli.

6. Deteksi Judul Berdasarkan Posisi dan Ukuran

Pipeline membedakan teks biasa, top title, dan hero title berdasarkan posisi dan ukuran bounding box. Hal ini penting karena judul biasanya perlu font lebih besar dan lebih tebal daripada teks biasa.

7. Heavy Keywords untuk Font Tebal

Daftar heavy_keywords digunakan untuk mengenali teks tertentu yang dianggap penting, seperti talent development, cyber security, cloud computing, research center, human resource, dan services.

Jika teks mengandung keyword tersebut, font weight dibuat menjadi 700, sehingga tampil lebih tebal pada output HTML.

8. Estimasi Warna Teks Menggunakan K-Means

Warna teks diperkirakan dengan K-Means clustering. Area crop teks biasanya terdiri dari warna background dan warna foreground. Dengan k=2, program mencoba memisahkan dua warna dominan tersebut dan memilih cluster yang lebih kecil sebagai warna teks.

9. Output HTML Dibuat Editable

HTML menggunakan contenteditable="true" agar pengguna dapat mengoreksi hasil secara manual. Ini penting karena OCR dan estimasi style tidak selalu sempurna, terutama pada gambar dengan layout kompleks.

10. JSON Metadata sebagai Data Layout

JSON metadata dibuat agar hasil ekstraksi tidak hanya tersedia dalam bentuk visual HTML, tetapi juga dalam bentuk data terstruktur. Data ini dapat digunakan untuk debugging, evaluasi, atau pengembangan fitur lanjutan.

Catatan Pengembangan

Beberapa pengembangan yang masih dapat dilakukan:

Meningkatkan akurasi deteksi font family.
Menambahkan deteksi ukuran font yang lebih presisi.
Menambahkan drag-and-drop untuk memindahkan teks di HTML.
Menambahkan resize handle untuk mengubah bounding box secara manual.
Menambahkan fitur save hasil edit HTML ke JSON.
Menambahkan export ke PowerPoint.
Menambahkan export ke PDF.
Menambahkan deteksi paragraf multi-line yang lebih akurat.
Menambahkan mode khusus untuk background kompleks.
Menambahkan integrasi vision-language model untuk estimasi style.
Menambahkan GUI agar pengguna tidak perlu menjalankan CLI.
Menghapus folder _tmp otomatis setelah proses selesai jika tidak diperlukan.
Contoh Workflow
1. Masukkan gambar ke folder input
input/
└── ekosistem.jpg
2. Jalankan pipeline
python pipeline.py --engine paddle --debug --cover-mode css
3. Buka hasil HTML
output/ekosistem_css_cover.html
4. Edit teks langsung di browser jika diperlukan

Klik teks pada HTML, lalu gunakan toolbar untuk mengubah font, ukuran, warna, alignment, atau format teks.

5. Cek metadata hasil ekstraksi
output/ekosistem_data.json
6. Cek ringkasan hasil seluruh proses
output/results.json
Kesimpulan

Project ini merupakan pipeline OCR dan layout reconstruction yang tidak hanya membaca teks dari gambar, tetapi juga mencoba membangun ulang tampilan visualnya dalam bentuk HTML. Dengan kombinasi OCR, preprocessing gambar, filter noise, style estimation, CSS cover, inpainting, dan editor HTML sederhana, sistem ini dapat digunakan sebagai dasar untuk eksperimen ekstraksi teks berbasis layout dan rekonstruksi dokumen visual.
