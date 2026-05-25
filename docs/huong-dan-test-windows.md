# Hướng dẫn Test cli-tran trên Windows

Hướng dẫn chi tiết từng bước để tự test và tìm lỗi trên Windows.
Dành cho người mới bắt đầu — không cần biết lập trình.

---

## Bước 1: Kiểm tra các yêu cầu trước khi cài đặt

Mở **PowerShell** (nhấn phím `Win`, gõ `powershell`, nhấn `Enter`).

### 1.1 Kiểm tra Python

```powershell
python --version
```

Phải hiện thị Python 3.10 trở lên. Ví dụ: `Python 3.12.0`

- Nếu báo lỗi `"python" is not recognized`: bạn chưa cài Python hoặc chưa thêm vào PATH.
  - Thử gõ: `py --version` (Windows Python launcher)
  - Nếu vẫn lỗi: tải và cài Python tại https://www.python.org/downloads/
  - **Lưu ý quan trọng:** Khi cài Python, nhớ tick chọn ô **"Add Python to PATH"**

### 1.2 Kiểm tra Antigravity CLI (agy)

```powershell
agy --version
```

Phải hiện thị số version, ví dụ: `1.0.2`

- Nếu báo lỗi: bạn chưa cài agy. Thử các lệnh sau để tìm:

```powershell
# Kiểm tra xem agy có ở các thư mục phổ biến không
dir "%LOCALAPPDATA%\agy\bin\agy.exe"
dir "%APPDATA%\npm\agy.cmd"
```

- Nếu không thấy file nào: cần cài đặt Antigravity CLI trước.

### 1.3 Kiểm tra đăng nhập Google

```powershell
agy -p "xin chào"
```

Phải trả lời được, ví dụ: `"Xin chào! Tôi có thể giúp gì cho bạn hôm nay?"`

- Nếu báo lỗi hoặc không có kết quả: bạn cần đăng nhập Google account trong agy.

---

## Bước 2: Cài đặt skill cli-tran

```powershell
# Tải về từ GitHub
git clone https://github.com/pnd4189/trans-windows
cd trans-windows

# Chạy cài đặt
python install.py
```

**Kết quả mong đợi:**
```
Repo:     ...
Staging:  ...
ExtDir:   ...
agy:      ...

Importing via agy...

Installed. Restart Antigravity CLI to load the extension.
```

- Nếu báo lỗi `agy not found in PATH`: quay lại Bước 1.2
- Nếu báo lỗi `agy plugin import failed`: thử chạy lại, hoặc kiểm tra agy đã được cài đúng chưa

---

## Bước 3: Chuẩn bị file test

Tạo 1 file văn bản nhỏ để test, ví dụ `test-novel.txt`:

```
第一章 开始

这是一个测试章节。主角李明走进了一片森林。

他看到了一只狐狸。狐狸对他说："你好，人类。"

李明非常惊讶。他从来没有见过会说话的动物。

"你是什么？"他问道。

狐狸笑了笑说："我是这片森林的守护者。"
```

Lưu file này ở bất kỳ đâu, ví dụ: `D:\test-novel.txt`

> **Lưu ý:** File phải được lưu dưới dạng UTF-8. Nếu dùng Notepad, chọn
> File → Save As → Encoding chọn **UTF-8**.

---

## Bước 4: Chạy test dịch

### 4.1 Mở agy (cửa sổ tương tác)

```powershell
agy
```

Đợi agy khởi động xong (hiện thị dấu nhắc prompt).

### 4.2 Chạy lệnh dịch

Trong cửa sổ agy, gõ:

```
/cli-tran D:\test-novel.txt
```

**Kết quả mong đợi:**
```
Translation complete: 1/1 chapters done, 0 skipped, 0 pending.
```

### 4.3 Nếu bị lỗi hoặc treo

Nhấn `Ctrl + C` để dừng. Sau đó đọc phần "Cách tìm và báo lỗi" bên dưới.

---

## Bước 5: Kiểm tra kết quả dịch

### 5.1 Tìm thư mục cache

```powershell
# Xem nơi lưu cache
dir "%LOCALAPPDATA%\cli-tran\novels"
```

Sẽ thấy 1 thư mục có tên là mã hash (ví dụ `4424de7c21297453`).

### 5.2 Xem file đã dịch

```powershell
# Thay <hash> bằng mã hash của bạn
dir "%LOCALAPPDATA%\cli-tran\novels\<hash>\chapter-output"
```

Phải có các file `chapter_001.txt`, `chapter_002.txt`...

Mở file kiểm tra: phải là tiếng Việt, **không có chữ Trung Quốc**.

### 5.3 Xem file tổng hợp

```powershell
type "C:\path\to\novel_vi.txt"
```

File này nằm cạnh file truyện gốc và có hậu tố `_vi.txt`.

---

## Cách Tìm Và Báo Lỗi

Khi gặp lỗi, hãy thu thập thông tin theo các bước sau rồi gửi báo cáo.

### Loại lỗi 1: Skill treo không chạy

**Hiện tượng:** Gõ `/cli-tran` nhưng không có gì xảy ra hoặc treo rất lâu.

**Cách kiểm tra:**

```powershell
# 1. Xem driver log — thay <hash> bằng mã hash của bạn
type "%LOCALAPPDATA%\cli-tran\novels\<hash>\driver.log"
```

**Thông tin cần gửi báo cáo:**
- Nội dung file `driver.log` (toàn bộ hoặc 50 dòng cuối)
- Bạn đã chạy từ cửa sổ agy hay PowerShell?

### Loại lỗi 2: Dịch xong nhưng file trống trơn

**Hiện tượng:** Báo thành công nhưng file chương trống không có nội dung.

**Cách kiểm tra:**

```powershell
# Xem debug log (nếu có)
dir "%LOCALAPPDATA%\cli-tran\novels\<hash>\debug"
type "%LOCALAPPDATA%\cli-tran\novels\<hash>\debug\chapter_001_raw.log"
```

**Thông tin cần gửi báo cáo:**
- Nội dung file debug (phần STDOUT và STDERR)
- Kích thước file chương: `dir "%LOCALAPPDATA%\cli-tran\novels\<hash>\chapter-output"`

### Loại lỗi 3: Báo "All backends exhausted"

**Hiện tượng:** Log hiển thị backend bị dead hoặc exhausted (hết quota).

**Cách kiểm tra:**

```powershell
# Xem trạng thái backend cache
type "%LOCALAPPDATA%\cli-tran\novels\<hash>\backend_cache.json"
```

- Nếu thấy `"alive": false`: xóa cache và thử lại:

```powershell
del "%LOCALAPPDATA%\cli-tran\novels\<hash>\backend_cache.json"
```

- Nếu báo quota: đợi khoảng 5-10 phút rồi chạy lại `/cli-tran --resume`

### Loại lỗi 4: Báo "agy CLI not installed"

**Hiện tượng:** Log báo không tìm thấy agy.

**Cách kiểm tra:**

```powershell
# Kiểm tra agy có chạy được không
agy -p "hello"

# Kiểm tra vị trí agy
where agy
dir "%LOCALAPPDATA%\agy\bin\agy.exe"
dir "%APPDATA%\npm\agy.cmd"
```

- Nếu `agy -p "hello"` chạy được nhưng skill vẫn báo lỗi: đó là bug, hãy báo cáo.

### Loại lỗi 5: Lỗi Python

**Hiện tượng:** Báo lỗi `ModuleNotFoundError`, `ImportError`, `SyntaxError`...

**Cách kiểm tra:**

```powershell
# Kiểm tra syntax các file
python -m py_compile "%LOCALAPPDATA%\cli-tran-src\scripts\translate-chapter.py"
python -m py_compile "%LOCALAPPDATA%\cli-tran-src\scripts\select-cascade.py"
python -m py_compile "%LOCALAPPDATA%\cli-tran-src\scripts\auto-translate.py"
python -m py_compile "%LOCALAPPDATA%\cli-tran-src\install.py"
```

- Nếu báo lỗi file nào: đó là bug, hãy gửi nội dung lỗi.

---

## Mẫu Báo Cáo Lỗi

Khi báo lỗi, hãy copy mẫu sau, điền thông tin và gửi:

```
## Thông tin hệ thống
- Phiên bản Windows: (ví dụ: Windows 11 Pro 23H2)
- Phiên bản Python: (kết quả của `python --version`)
- Phiên bản agy: (kết quả của `agy --version`)
- Phiên bản cli-tran: (commit hash hoặc ngày tải về)

## Mô tả lỗi
- Lệnh đã chạy: (ví dụ: `/cli-tran D:\test.txt`)
- Kết quả mong đợi: (ví dụ: dịch thành công)
- Kết quả thực tế: (ví dụ: treo không có kết quả)

## Log lỗi
(Dán nội dung từ driver.log hoặc debug log vào đây)

## Các bước đã thử
- [ ] Đã xóa backend_cache.json và chạy lại
- [ ] Đã kiểm tra agy -p "hello" chạy được
- [ ] Đã kiểm tra file nguồn là UTF-8
```

---

## Các lệnh hữu ích

```powershell
# Xem tiến độ dịch
python "%LOCALAPPDATA%\cli-tran-src\scripts\get-progress.py" "<đường-dẫn-state-file>"

# Tiếp tục sau khi bị gián đoạn
# (Chạy trong cửa sổ agy)
/cli-tran --resume

# Chọn lại các chương lỗi để dịch lại
# (Chạy trong cửa sổ agy)
/cli-tran --redo failed

# Xem trạng thái backend
type "%LOCALAPPDATA%\cli-tran\novels\<hash>\backend_cache.json"

# Xem log chi tiết
type "%LOCALAPPDATA%\cli-tran\novels\<hash>\driver.log"

# Kiểm tra file gốc có phải UTF-8 không
python -c "open(r'D:\test.txt', encoding='utf-8').read(); print('UTF-8 OK')"
```
