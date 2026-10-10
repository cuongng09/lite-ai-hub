---
name: code-review-vi
description: Checklist rà soát mã nguồn chuyên nghiệp bằng tiếng Việt: bảo mật, hiệu năng, clean code
---
# Code Review Vietnam Skill

Khi nhận được yêu cầu review code từ người dùng, hãy đánh giá theo checklist 4 tiêu chí sau:
1. **Tính đúng đắn & Logic**:
   - Có lỗi logic, ngoại lệ tiềm ẩn (Null Pointer, Index Out of Range, Off-by-one) không?
   - Xử lý các edge cases (danh sách rỗng, đầu vào bất hợp lệ, timeout) như thế nào?
2. **Hiệu năng & Tài nguyên**:
   - Độ phức tạp thời gian/không gian thuật toán ($O(N)$, $O(N^2)$)?
   - Có hiện tượng memory leak, đóng file/kết nối thiếu an toàn không?
3. **Bảo mật**:
   - Lỗ hổng SQL Injection, Command Injection, XSS, Path Traversal, Hardcoded Secrets?
4. **Clean Code & Khả năng bảo trì**:
   - Đặt tên biến/hàm có mang tính biểu cảm không?
   - Cung cấp đoạn code sau khi đã refactor tối ưu và giải thích rõ điểm thay đổi.
