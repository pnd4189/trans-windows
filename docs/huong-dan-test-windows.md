# Huong dan Test cli-tran tren Windows

Huong dan chi tiet tung buoc de tu test va tim loi tren Windows.
Danh cho nguoi moi bat dau — khong can biet lap trinh.

---

## Buoc 1: Kiem tra cac yeu cau truoc khi cai dat

Mo **PowerShell** (nhan `Win`, go `powershell`, nhan `Enter`).

### 1.1 Kiem tra Python

```powershell
python --version
```

Phai hien thi Python 3.10 tro len. Vi du: `Python 3.12.0`

- Neu bao loi `"python" is not recognized`: ban chua cai Python hoac chua them vao PATH.
  - Thu: `py --version` (Windows Python launcher)
  - Neu van loi: tai va cai Python tai https://www.python.org/downloads/
  - **Luu y:** Khi cai Python, tick chon "Add Python to PATH"

### 1.2 Kiem tra Antigravity CLI (agy)

```powershell
agy --version
```

Phai hien thi version, vi du: `1.0.2`

- Neu bao loi: ban chua cai agy. Thu cac lenh sau:

```powershell
# Kiem tra xem agy co trong cac thu muc pho biep khong
dir "%LOCALAPPDATA%\agy\bin\agy.exe"
dir "%APPDATA%\npm\agy.cmd"
```

- Neu khong thay file nao: can cai dat Antigravity CLI truoc.

### 1.3 Kiem tra dang nhap Google

```powershell
agy -p "xin chao"
```

Phai tra loi duoc, vi du: `"Xin chao! Toi co the giup gi cho ban hom nay?"`

- Neu bao loi hoac khong co ket qua: ban can dang nhap Google account trong agy.

---

## Buoc 2: Cai dat skill cli-tran

```powershell
# Tai ve (hoac clone tu git)
git clone https://github.com/pnd4189/trans-windows
cd trans-windows

# Chay cai dat
python install.py
```

**Ket qua mong doi:**
```
Repo:     ...
Staging:  ...
ExtDir:   ...
agy:      ...

Importing via agy...

Installed. Restart Antigravity CLI to load the extension.
```

- Neu bao loi `agy not found in PATH`: quay lai Buoc 1.2
- Neu bao loi `agy plugin import failed`: thu chay lai, hoac kiem tra agy da duoc cai dung chua

---

## Buoc 3: Chuan bi file test

Tao 1 file van ban nho de test, vi du `test-novel.txt`:

```
第一章 开始

这是一个测试章节。主角李明走进了一片森林。

他看到了一只狐狸。狐狸对他说："你好，人类。"

李明非常惊讶。他从来没有见过会说话的动物。

"你是什么？"他问道。

狐狸笑了笑说："我是这片森林的守护者。"
```

Luu file nay o bat ky dau, vi du: `D:\test-novel.txt`

---

## Buoc 4: Chay test dich

### 4.1 Mo agy (cua so interactive)

```powershell
agy
```

Doi agy khoi dong xong (hien thi prompt).

### 4.2 Chay lenh dich

Trong cua so agy, go:

```
/cli-tran D:\test-novel.txt
```

**Ket qua mong doi:**
```
Translation complete: X/Y chapters done, 0 skipped, 0 pending.
```

### 4.3 Neu bi loi hoac treo

Nhan `Ctrl + C` de dung. Sau do doc phan "Cach tim va bao loi" ben duoi.

---

## Buoc 5: Kiem tra ket qua dich

### 5.1 Tim thu muc cache

```powershell
# Xem noi luu cache
dir "%LOCALAPPDATA%\cli-tran\novels"
```

Se thay 1 thu muc co ten la ma hash (vi du `4424de7c21297453`).

### 5.2 Xem file da dich

```powershell
# Thay <hash> bang ma hash cua ban
dir "%LOCALAPPDATA%\cli-tran\novels\<hash>\chapter-output"
```

Phai co cac file `chapter_001.txt`, `chapter_002.txt`...

Mo file kiem tra: phai la tieng Viet, khong co chu Trung Quoc.

### 5.3 Xem file tong hop

```powershell
type "%LOCALAPPDATA%\cli-tran\novels\<hash>\translated_novel.txt"
```

---

## Cach Tim Va Bao Loi

Khi gap loi, hay thu thap thong tin theo cac buoc sau roi gui bao cao.

### Loai loi 1: Skill treo khong chay

**Hien tuong:** Go `/cli-tran` nhung khong co gi xay ra hoac treo rat lau.

**Cach kiem tra:**

```powershell
# 1. Xem driver log
type "%LOCALAPPDATA%\cli-tran\novels\<hash>\driver.log"
```

**Thong tin can gui bao cao:**
- Noi dung file `driver.log` (toan bo hoac 50 dong cuoi)
- Ban da chay tu cua so agy hay PowerShell?

### Loai loi 2: Dich ra nhung file trong

**Hien tuong:** Bao thanh cong nhung file chapter trong troi.

**Cach kiem tra:**

```powershell
# Xem debug log (neu co)
dir "%LOCALAPPDATA%\cli-tran\novels\<hash>\debug"
type "%LOCALAPPDATA%\cli-tran\novels\<hash>\debug\chapter_001_raw.log"
```

**Thong tin can gui bao cao:**
- Noi dung file debug (STDOUT va STDERR)
- Kich thuoc file chapter: `dir "%LOCALAPPDATA%\cli-tran\novels\<hash>\chapter-output"`

### Loai loi 3: Bao "All backends exhausted"

**Hien tuong:** Log hien thi backend bi dead hoac exhausted.

**Cach kiem tra:**

```powershell
# Xem backend cache
type "%LOCALAPPDATA%\cli-tran\novels\<hash>\backend_cache.json"
```

- Neu `"alive": false`: xoa cache va thu lai:

```powershell
del "%LOCALAPPDATA%\cli-tran\novels\<hash>\backend_cache.json"
```

- Neu bao quota: doi khoang 5-10 phut roi chay lai `/cli-tran --resume`

### Loai loi 4: Bao "agy CLI not installed"

**Hien tuong:** Log bao khong tim thay agy.

**Cach kiem tra:**

```powershell
# Kiem tra agy co chay duoc khong
agy -p "hello"

# Kiem tra vi tri agy
where agy
dir "%LOCALAPPDATA%\agy\bin\agy.exe"
dir "%APPDATA%\npm\agy.cmd"
```

- Neu `agy -p "hello"` chay duoc nhung skill bao loi: do la bug, hay bao cao.

### Loai loi 5: Loi Python

**Hien tuong:** Bao loi `ModuleNotFoundError`, `ImportError`, `SyntaxError`...

**Cach kiem tra:**

```powershell
# Kiem tra syntax cac file
python -m py_compile "%LOCALAPPDATA%\cli-tran-src\scripts\translate-chapter.py"
python -m py_compile "%LOCALAPPDATA%\cli-tran-src\scripts\select-cascade.py"
python -m py_compile "%LOCALAPPDATA%\cli-tran-src\scripts\auto-translate.py"
python -m py_compile "%LOCALAPPDATA%\cli-tran-src\install.py"
```

- Neu bao loi file nao: do la bug, hay gui noi dung loi.

---

## Mau Bao Cao Loi

Khi bao loi, hay copy va dien vao mau sau:

```
## Thong tin he thong
- Windows version: (vi du: Windows 11 Pro 23H2)
- Python version: (ket qua cua `python --version`)
- agy version: (ket qua cua `agy --version`)
- cli-tran version: (commit hash hoac ngay tai ve)

## Mo ta loi
- Lenh da chay: (vi du: `/cli-tran D:\test.txt`)
- Ket qua mong doi: (vi du: dich thanh cong)
- Ket qua thuc te: (vi du: treo khong co ket qua)

## Log loi
(Dan noi dung tu driver.log hoac debug log vao day)

## Cac buoc da thu
- [ ] Da xoa backend_cache.json va chay lai
- [ ] Da kiem tra agy -p "hello" chay duoc
- [ ] Da kiem tra file source la UTF-8
```

---

## Cac lenh huu ich

```powershell
# Xem tien do
python "%LOCALAPPDATA%\cli-tran-src\scripts\get-progress.py" "<state-file>"

# Resume sau khi bi gian doan
# (Chay trong cua so agy)
/cli-tran --resume

# Reset cac chapter loi de dich lai
# (Chay trong cua so agy)
/cli-tran --redo failed

# Xem trang thai backend
type "%LOCALAPPDATA%\cli-tran\novels\<hash>\backend_cache.json"

# Xem log chi tiet
type "%LOCALAPPDATA%\cli-tran\novels\<hash>\driver.log"

# Kiem tra file goc co phai UTF-8 khong
python -c "open(r'D:\test.txt', encoding='utf-8').read(); print('OK')"
```
