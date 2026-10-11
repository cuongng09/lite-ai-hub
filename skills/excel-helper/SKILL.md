---
name: excel-helper
description: Hướng dẫn công thức và thao tác Excel, Google Sheets. Dùng khi người dùng hỏi "công thức", "hàm", "VLOOKUP", "XLOOKUP", "SUMIF", "IF", "pivot table", "tính tổng/đếm/lọc trong Excel", hoặc mô tả một bảng tính và muốn tính toán.
---

# Trợ lý Excel / Google Sheets

## Bước 1: Hiểu bảng tính
Cần biết: dữ liệu nằm ở cột/ô nào, muốn tính gì, đang dùng Excel hay Google Sheets (nếu quan trọng, vì một số hàm khác nhau). Nếu thiếu cột/ô cụ thể, hỏi một câu hoặc dùng ví dụ giả định và nói rõ đó là giả định.

## Bước 2: Trả lời theo khung
1. **Công thức** đặt trong khối code, sẵn sàng sao chép:
   ```
   =SUMIFS(C:C, A:A, "Hà Nội", B:B, ">=2025")
   ```
2. **Giải thích từng phần:** mỗi đối số làm gì.
3. **Ví dụ:** một mini-bảng với kết quả dự kiến.
4. **Lưu ý:** lỗi thường gặp (`#N/A`, `#VALUE!`, ô bị lưu dạng văn bản, dấu `,` hay `;` tuỳ cài đặt vùng).

## Quy tắc
- Ưu tiên hàm phổ biến, ngắn gọn. Có hàm mới tốt hơn (ví dụ XLOOKUP so với VLOOKUP) thì nêu cả hai và nói phiên bản nào hỗ trợ.
- Nhiều trường hợp có thể cần dấu `;` thay `,` ở máy đặt vùng Việt Nam: nhắc một câu nếu công thức bị báo lỗi cú pháp.
- Với thao tác không dùng công thức (pivot, lọc, định dạng có điều kiện), hướng dẫn từng bước đánh số theo tên menu.
- Không bịa tên hàm. Không chắc thì nói rõ.
- Nếu người dùng dán thông báo lỗi, giải thích nguyên nhân khả dĩ nhất trước, rồi cách sửa.
