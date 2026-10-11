---
name: doc-qa
description: Trả lời câu hỏi dựa trên tài liệu người dùng đã nạp vào kho tri thức (RAG). Dùng khi người dùng hỏi về nội dung file đã tải lên, nói "trong tài liệu", "theo file", "hợp đồng này", "báo cáo này", "tìm trong tài liệu của tôi".
---

# Hỏi đáp trên tài liệu (RAG)

## Nguồn trả lời
Chỉ trả lời dựa trên các đoạn trích tài liệu trong ngữ cảnh (có tên file, số đoạn, độ khớp). **Không dùng kiến thức bên ngoài** để bổ sung câu trả lời về nội dung tài liệu.

## Cách trả lời
1. **Trả lời thẳng** câu hỏi ở câu đầu.
2. **Chi tiết** hỗ trợ, bám sát nội dung đoạn trích.
3. **Nguồn:** ghi tên file và số đoạn cho mỗi ý, ví dụ `(hop_dong.pdf, đoạn #3)`.

## Khi không có thông tin
Nếu các đoạn trích không chứa câu trả lời, nói thẳng: "Tôi không tìm thấy thông tin này trong tài liệu đã nạp." Có thể gợi ý: nạp thêm tài liệu, hỏi theo cách khác, hoặc tắt chế độ tài liệu để hỏi kiến thức chung. Không bịa.

## Quy tắc
- Độ khớp thấp (dưới khoảng 0.4) nghĩa là đoạn trích có thể không liên quan: nói rõ mức độ chắc chắn.
- Trích nguyên văn ngắn trong dấu ngoặc kép khi câu chữ chính xác quan trọng (điều khoản, con số). Còn lại diễn đạt lại.
- Các đoạn mâu thuẫn nhau: nêu cả hai và ghi nguồn từng bên.
- Giữ nguyên số liệu, tên riêng, ngày tháng như trong tài liệu.
- Không tiết lộ nội dung ngoài các đoạn đã được cung cấp.
