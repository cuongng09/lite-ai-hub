---
name: quiz-to-word
description: Tạo bộ 60 hoặc nhiều hơn câu hỏi trắc nghiệm tổng hợp từ các tài liệu học tập, giáo trình, bài giảng và xuất ra cấu trúc tài liệu ôn tập chuẩn (kèm nút tải file Word .docx). Dùng khi người dùng yêu cầu ra đề thi, tạo 60 câu hỏi ôn tập, xuất câu hỏi ra Word, tổng hợp câu hỏi từ nhiều tài liệu PDF/Word.
---

# Tạo bộ câu hỏi trắc nghiệm ôn tập (Quiz to Word)

## Nhiệm vụ chính
Khi nhận được yêu cầu từ người dùng hoặc kích hoạt qua `/quiz-to-word`:
1. Phân tích toàn diện nguồn tài liệu được cung cấp (văn bản dán vào, nội dung trích xuất từ các file đính kèm, hoặc dữ liệu từ kho RAG).
2. Tạo bộ câu hỏi trắc nghiệm ôn tập chất lượng cao với số lượng theo yêu cầu (mặc định là **60 câu hỏi**, hoặc nhiều hơn như 100, 160 câu khi tổng hợp từ nhiều tài liệu như LKDT, Linh kiện bán dẫn, LKBD tổ hợp, LKBD quang điện).
3. Đính kèm **Thời gian tạo (Date/Time)** ở đầu bộ đề và trong phần đáp án.

## Quy tắc thiết kế câu hỏi
- **Số lượng câu hỏi**:
  - Tạo đủ số lượng người dùng yêu cầu (ví dụ: 60 câu, hoặc 40 câu x 4 tài liệu = 160 câu).
  - Phân bổ đều các chủ đề, chương, phần của tài liệu nguồn.
  - **Quy tắc khi thiếu dữ liệu**: Nếu nội dung tài liệu nguồn quá ngắn hoặc không đủ kiến thức để tạo đủ số lượng yêu cầu mà không bị trùng lặp/bịa đặt, hãy tạo tối đa số lượng câu hỏi chất lượng nhất có thể và ghi rõ:
    > *⚠️ Ghi chú: Do dung lượng tài liệu nguồn giới hạn, hệ thống đã tối ưu tạo X câu hỏi chất lượng cao nhất bám sát tuyệt đối nội dung nguồn.*
- **Cấu trúc mỗi câu hỏi**:
  - Câu hỏi rõ ràng, một ý trọng tâm, không đánh đố vô lý.
  - 4 phương án lựa chọn: **A, B, C, D**.
  - Chỉ có **duy nhất 1 đáp án đúng**.
  - Các đáp án gây nhiễu phải hợp lý, liên quan trực tiếp đến kiến thức trong bài.
  - Xáo trộn vị trí đáp án đúng đều giữa A, B, C, D.
- **Thời gian (Date/Time)**:
  - Luôn ghi rõ ngày giờ tạo bộ câu hỏi ngay dưới tiêu đề.

## Định dạng hiển thị
Luôn trình bày theo 2 phần rõ rệt để người học có thể tự kiểm tra trước khi tra đáp án:

```markdown
# BỘ CÂU HỎI TRẮC NGHIỆM ÔN TẬP
*Thời gian tạo: [Thời gian hiện tại]*
*Nguồn tài liệu: [Tên các tài liệu tổng hợp]*
*Tổng số câu: [Số lượng câu]*

---

## PHẦN 1: NỘI DUNG CÂU HỎI

Câu 1: [Nội dung câu hỏi]
A. [Phương án A]
B. [Phương án B]
C. [Phương án C]
D. [Phương án D]

Câu 2: [Nội dung câu hỏi]
...

---

## PHẦN 2: BẢNG ĐÁP ÁN & GIẢI THÍCH CHI TIẾT
*Thời gian hoàn thành: [Thời gian hiện tại]*

| Câu | Đáp án | Giải thích tóm tắt kiến thức nguồn |
| :---: | :---: | :--- |
| 1 | A | [Giải thích lý do vì sao A đúng dựa trên tài liệu] |
| 2 | C | [Giải thích ngắn gọn] |
...
```

Cuối phản hồi, hướng dẫn người dùng:
> *💡 Bạn có thể bấm nút **"📥 Tải Word (.docx)"** ngay phía dưới phản hồi để lưu file Word về máy ôn tập offline.*
