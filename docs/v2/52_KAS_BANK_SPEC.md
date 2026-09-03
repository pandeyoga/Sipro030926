# 52 — Kas & Bank (Fase 82): rekening/kas sebagai entitas akuntansi + analisis gap

## 1. Masalah yang ditutup
Sebelum Fase 82 uang perusahaan hanya diwakili dua akun GL (`1-1100 Kas`, `1-1200 Bank`). Master
rekening bank (Fase 47A) ada, tetapi semua rekening menunjuk `1-1200` yang sama; penerimaan AR,
pembayaran AP, komisi, kas bon, pajak, refund, dan pencairan KPR tidak menyebut rekening mana yang
dipakai. Akibat akuntansinya fatal: **saldo per rekening tidak ada**, rekonsiliasi bank hanya bisa
di level total, tidak ada buku kas/bank, tidak ada transfer antar rekening / setor / tarik tunai,
saldo awal rekening tidak dijurnal (neraca ≠ rekening), dan kas kecil tidak punya saldo.

## 2. Model
| Konsep | Implementasi |
|---|---|
| Akun induk | `1-1100`, `1-1200` ditandai `is_header=True`; **tidak boleh menerima posting**. `post_journal` otomatis mengarahkan baris di akun induk ke sub-akun rekening yang dipilih (`cash_account_id` di baris) atau rekening/kas **default** jenis itu. |
| Sub-akun | Setiap rekening/kas punya sub-akun: bank `1-1201..1-1299` (parent `1-1200`), kas `1-1101..1-1199` (parent `1-1100`). Nama = `"<Bank> — <nama rekening>"`. Prefix `1-11`/`1-12` tetap terbaca oleh laporan arus kas & neraca (klasifikasi via prefix). |
| Master terpadu | Koleksi `bank_accounts` diperluas: `kind` (`bank`/`cash`), `is_default` per jenis, `opening_balance`, `opening_date`, `opening_posted`, `opening_journal_id`. Rekening lama Fase 47 tetap dipakai (rekonsiliasi bank tidak berubah). |
| Saldo awal | Dijurnal otomatis saat rekening dibuat/diubah (sekali): Dr sub-akun / Cr `3-1950 Saldo Awal Kas & Bank` (ekuitas), `source_event=cashbank.opening:<id>` (idempoten). Setelah dijurnal, saldo awal terkunci. |
| Migrasi | `cash_bank.ensure_setup()` saat startup (awal & akhir lifespan, per org): backfill `kind`, bootstrap Kas Besar (`KAS-01`, `1-1101`) & Rekening Operasional bila kosong, sub-akun untuk rekening yang masih menumpang `1-1200`, pilih default, posting saldo awal, **pindahkan baris jurnal lama di akun induk ke rekening default** (`migrated_from` disimpan). Idempoten. |
| Wiring aliran uang | `cash_account_id` opsional di: `POST /finance/ar/receipts`, `POST /finance/ap/bills/{id}/pay` & `/pay-withholding`, `POST /finance/commissions/{id}/pay`, `POST /petty-cash/advances/{id}/disburse` (+ pengembalian sisa memakai rekening yang sama), `PUT /tax/records/{id}` (setor), `POST /cancellations/{id}/refund`, `POST /contracts/{id}/kpr/stage/pencairan`, `POST /financing/{id}/disburse`. Dokumen (kuitansi, payments_out, kas bon, komisi, pencairan KPR) menyimpan `cash_account_id/_name/_code`. Rekening fiktif/nonaktif → 400 di muka; tanpa id → default jenis (bank untuk transfer/KPR, kas untuk tunai). |
| Rekonsiliasi bank | `bank_match._apply` kini memakai rekening mutasi sebagai `cash_account_id` (AR, AP) dan sub-akunnya untuk biaya bank / jasa giro; pembatalan kuitansi membalik ke sub-akun kuitansi. |
| Transfer internal | Koleksi `cash_transfers` (`TRF/<tahun>/<n>`): `transfer`, `setor_tunai` (kas→bank), `tarik_tunai` (bank→kas), `isi_kas_kecil` (→kas). Status `pending → posted/rejected`. **SoD**: pembuat ≠ penyetuju; approve butuh izin `bank:approve` (finance_manager/owner/super_admin). Saldo asal harus cukup (nominal + biaya). Jurnal: Dr tujuan / Cr asal (nominal+biaya) / Dr `6-1600` biaya. |
| Buku Kas & Bank | `GET /cash-bank/book?account_id&date_from&date_to[&format=csv]`: saldo awal (Σ sebelum periode), mutasi dengan lawan akun & saldo berjalan, total masuk/keluar, CSV `;`. |
| Posisi Kas | `GET /cash-bank/position`: saldo buku tiap rekening, total kas/bank, mutasi bulan berjalan, daftar saldo negatif (jujur, bukan disembunyikan), transfer menunggu. |

### Endpoint `/cash-bank` (RBAC resource `bank`)
`GET /accounts[?active&kind]`, `POST /accounts`, `PUT /accounts/{id}`, `POST /accounts/{id}/set-default`,
`GET /position`, `GET /book`, `GET /transfers[?status]`, `POST /transfers`, `POST /transfers/{id}/approve|reject`.

### UI
Menu **Keuangan › Kas & Bank** (`/cash-bank`): tab Posisi Kas · Buku Kas & Bank (+CSV) · Transfer Internal
(ajukan/setujui/tolak) · Master Rekening & Kas. Komponen `CashAccountSelect` (memuat rekening aktif +
saldo, auto-pilih default per jenis) disematkan di: dialog Penerimaan AR, Bayar Tagihan AP, Pencairan
Kas Bon, Setor Pajak (status "paid"), Bayar Refund pembatalan, dan tahap **Pencairan KPR**
("Dana KPR masuk ke rekening" — default rekening bank default; sebaiknya rekening escrow).

### Pencairan KPR — wiring rekening (permintaan user)
Alur: bank KPR mencairkan → `KprPanel` tahap *pencairan* (atau `/financing/{id}/disburse`) mengirim
`cash_account_id` → `kpr_disburse.disburse()` → `finance_engine.apply_receipt(method="kpr", cash_account_id)`
→ kuitansi KWT menyimpan rekening → event `payment.received{cash_account_id}` → jurnal Dr **sub-akun
rekening penerima** / Cr `2-1400`. Entri pencairan di `financing.disbursements[]` menyimpan
`cash_account_id/_name`. Kelebihan (titipan) ikut ke rekening yang sama.

## 3. Uji & gate
- `backend/tests/test_p82_cash_bank.py` (4): master & default, saldo awal + CSV + duplikat, transfer SoD/posting/saldo/jurnal, kuitansi & jurnal mendarat di rekening pilihan + rekening fiktif ditolak.
- Gate lama disesuaikan ke sub-akun: `verify_f26_money.py` (`gl_balance` Σ sub-akun), `verify_p27_money.py` (`tb()` agregasi induk), `verify_quotation_labor.py`, `verify_tax_compliance.py`, `test_p76_78_allin_kpr.py`, `test_p78_ui_api.py`; `verify_bank_recon.py` kini memilih kuitansi hasil pencocokan (bukan kuitansi booking fee — bug gate pre-existing).

## 4. Analisis gap Finance & Accounting yang tersisa (backlog terurut)
**P0 — akuntansi belum utuh**
1. **Rekonsiliasi bank ↔ sub-akun**: `bank/accounts/{id}/reconciliation` masih membandingkan saldo rekening vs saldo buku total; harus per sub-akun + laporan selisih beralasan (outstanding cheque/deposit in transit) dan *statement closing balance* per periode.
2. **Kas kecil (imprest)**: pengeluaran langsung kas kecil (bukan kas bon) dengan bukti & kategori beban, batas imprest, replenish otomatis mengusulkan `isi_kas_kecil` saat saldo < ambang.
3. **Tutup periode Kas & Bank**: jurnal ke rekening tidak boleh bertanggal di periode yang sudah direkonsiliasi; kunci saldo awal per bulan.
4. **Cek/giro mundur (PDC)**: penerimaan giro = akun `1-1300 Giro Belum Cair`, baru jadi bank saat kliring; tolakan giro.
5. **Pembayaran massal (payment run) & bukti kas keluar (BKK) / kas masuk (BKM)** bernomor dan tercetak; sekarang uang keluar tersebar per modul tanpa dokumen kas standar.

**P1 — pelaporan & kontrol**
6. Laporan arus kas langsung per rekening (bukan hanya klasifikasi operasi/investasi/pendanaan).
7. Aging AR/AP sudah ada tetapi belum ada **jadwal pembayaran vendor (cash forecast) vs posisi kas** → peringatan kas tidak cukup.
8. Mata uang & bunga: rekening valas, bunga deposito otomatis, biaya admin bulanan terjadwal.
9. Limit otorisasi berjenjang untuk transfer (nominal > X butuh dua penyetuju).
10. Jurnal koreksi rekening (reklas antar sub-akun) dengan alasan wajib + jejak.

**P2 — hal yang belum menyebut rekening (masih ke default)**
11. Pembayaran upah harian (`labor_engine.pay_payroll`), marketing fee, pinjaman korporat (pencairan/angsuran), perolehan aset tetap, kuitansi biaya all-in (`cost_receipt`), booking fee — sudah benar di sub-akun default, tetapi UI-nya belum menyediakan pemilih rekening.
12. Ekspor buku kas ke XLSX/PDF bertanda tangan; impor mutasi otomatis (open banking/ CSV terjadwal).
