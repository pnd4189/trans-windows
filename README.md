# cli-tran

Công cụ dịch tiểu thuyết Trung → Việt tự động qua Antigravity CLI.
Chỉ cần 1 lệnh để dịch cả cuốn tiểu thuyết (~500 chương) không cần can thiệp tay.

## Yêu cầu

- [Antigravity CLI](https://github.com/google-antigravity/antigravity-cli) (`agy`) — đã cài và có trong PATH
- Python 3.10 trở lên — gõ `python --version` trong terminal phải chạy được

## Cài đặt

```bash
git clone https://github.com/pnd4189/trans-windows
cd trans-windows
python install.py
```

`install.py` sẽ copy file vào thư mục staging, triển khai extension tại
`~/.gemini/extensions/cli-tran/`, và đăng ký plugin qua
`agy plugin import gemini`. Khởi động lại Antigravity CLI sau khi cài.

## Cách dùng

```
/cli-tran /path/to/novel.txt           # Khởi tạo + dịch toàn bộ
/cli-tran --resume                     # Tiếp tục bản dịch bị gián đoạn
/cli-tran --status                     # Xem tiến độ
/cli-tran --redo 3,7,11-15             # Chọn lại các chương cần dịch lại
```

Skill chạy một Python driver dịch từng chương qua subprocess độc lập.
Nó tiếp tục cho đến khi mọi chương `completed` hoặc `skipped`,
sau đó gộp thành 1 file `*_vi.txt` cạnh file gốc.

## Kiến trúc

```
/cli-tran <file>
  │
  ├─ scripts/init-translation.py     # Phát hiện chương, tạo state.json
  │
  └─ scripts/auto-translate.py       # Vòng lặp driver — chạy đến khi xong
       ├─ scripts/select-cascade.py       # Chọn backend agy
       ├─ scripts/translate-chapter.py    # 1 subprocess mỗi chương
       └─ scripts/advance-chapter.py      # Kiểm tra output + cập nhật state
            └─ scripts/merge-chapters.py  # Gộp file khi hoàn thành
```

State của mỗi cuốn tiểu thuyết nằm trong thư mục cache theo hệ điều hành:
- **Linux/macOS**: `~/.cache/cli-tran/novels/<hash>/state.json`
- **Windows**: `%LOCALAPPDATA%\cli-tran\novels\<hash>\state.json`

An toàn khi Ctrl+C bất kỳ lúc nào — `/cli-tran --resume` sẽ tiếp tục từ chương
dừng cuối cùng.

## Backend

| Ưu tiên | Backend | Model |
|----------|---------|-------|
| 1 | agy subprocess | Cấu hình trong Antigravity settings |

Driver kiểm tra binary agy có sẵn không (không gọi subprocess probe).
Cache âm 5 phút ngăn kiểm tra lại backend đã chết; cache dương 1 giờ
bỏ qua kiểm tra khi backend vẫn tốt. Khi backend hết quota, driver dừng
sạch và báo bạn chạy lại sau bằng `/cli-tran --resume`.

## Thể loại hỗ trợ

| Mã thể loại | Mô tả |
|------------|--------|
| `tienxia`  | Tiên Hiệp |
| `wuxia`    | Kiếm Hiệp |
| `urban`    | Thành Thị |
| `historical` | Lịch Sử |
| `gamelit`  | Hệ thống / Game |
| `horror`   | Kinh Dị |
| `fantasy`  | Fantasy (mặc định) |

Thể loại được tự động phát hiện từ 8KB đầu tiên của file gốc.

## Cấu trúc project

```
├── install.py                  # Cài đặt đa nền tảng + đăng ký plugin agy
├── gemini-extension.json       # Extension manifest (Antigravity đọc file này)
├── plugin.json                 # Plugin metadata
├── GEMINI.md                   # Context file được skill load
├── hooks/
│   └── hooks.json              # Rỗng — kiến trúc driver không cần hooks
├── skills/
│   └── cli-tran/
│       └── SKILL.md            # Định nghĩa slash-command
├── scripts/
│   ├── auto-translate.py       # Vòng lặp driver chính
│   ├── translate-chapter.py    # Dịch 1 chương qua agy subprocess
│   ├── select-cascade.py       # Chọn backend + cache logic
│   ├── advance-chapter.py      # Kiểm tra output + cập nhật state.json
│   ├── init-translation.py     # Khởi tạo cache + state cho tiểu thuyết
│   ├── detect-chapters.py      # Phát hiện ranh giới chương
│   ├── merge-chapters.py       # Gộp file chương thành file hoàn chỉnh
│   ├── merge-entities.py       # Tích lũy glossary entities
│   ├── redo-chapters.py        # Reset chương về trạng thái chờ dịch
│   ├── get-progress.py         # Hiển thị tiến độ
│   ├── recover-state.py        # Khôi phục state bị hỏng
│   ├── validate-translation.py # Kiểm tra chất lượng bản dịch
│   ├── epub2txt.py             # Chuyển EPUB sang text
│   └── lib/
│       ├── platform-paths.py   # Xử lý đường dẫn đa nền tảng
│       ├── file-lock.py        # Khóa file đa nền tảng
│       └── novel_cache.py      # Quản lý thư mục cache
├── glossary/
│   ├── default.json            # Thuật ngữ chung
│   └── genres/                 # Override theo thể loại
└── references/                 # Nguyên tắc dịch + hướng dẫn đại từ
```

## Kiểm soát chất lượng

- **Phát hiện rò rỉ CJK**: bản dịch có >5% ký tự Trung sẽ bị từ chối và
  tự động thử lại (tối đa 5 lần mỗi chương trước khi bỏ qua).
- **Glossary first-seen-wins**: một khi `李明 → Lý Minh` đã được ghi trong
  `novel-glossary.json`, nó được áp dụng nhất quán cho tất cả chương sau.
- **Ghi file atomic**: file chương và state.json được ghi qua temp + replace
  để tránh hỏng khi bị ngắt giữa chừng.
- **Khóa file đa nền tảng**: `advance-chapter.py` khóa độc quyền trước khi
  sửa state, ngăn nhiều tiến trình cùng ghi gây hỏng dữ liệu.

## Lưu ý cho Windows

- **Python trong PATH**: đảm bảo `python --version` chạy được trong terminal.
  Nếu chỉ có `py` launcher, thêm Python vào PATH hoặc dùng `py` thay thế.
- **Đường dẫn dài**: nếu username Windows quá dài và đường dẫn cache vượt
  260 ký tự, bật `LongPathsEnabled` trong registry hoặc đặt biến
  `CLI_TRAN_CACHE_ROOT` thành đường dẫn ngắn hơn.
- **Di chuyển state**: dữ liệu cache từ Linux không dùng được trên Windows —
  cần khởi tạo dịch mới trên máy khác.

## Giấy phép

MIT
