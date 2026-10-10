---
name: diagram-mermaid
description: Hướng dẫn vẽ sơ đồ Mermaid an toàn, chọn đúng loại sơ đồ và cú pháp chuẩn không lỗi render
---
# Diagram Mermaid Skill

Khi người dùng yêu cầu vẽ sơ đồ quy trình, kiến trúc hệ thống, luồng dữ liệu hoặc biểu đồ quan hệ:
1. Chọn đúng loại sơ đồ:
   - Sơ đồ luồng/quy trình: Dùng `flowchart TD` (từ trên xuống) hoặc `flowchart LR` (từ trái sang phải).
   - Sơ đồ tuần tự: Dùng `sequenceDiagram`.
   - Sơ đồ trạng thái: Dùng `stateDiagram-v2`.
   - Sơ đồ quan hệ thực thể: Dùng `erDiagram`.
   - Sơ đồ lớp hướng đối tượng: Dùng `classDiagram`.
2. Quy tắc an toàn để tránh lỗi cú pháp:
   - Đặt nhãn node trong dấu ngoặc kép nếu có ký tự đặc biệt: `id["Nhãn (Chi tiết)"]`.
   - Tuyệt đối không dùng thẻ HTML thô (`<br>`, `<b>`) bên trong nhãn node.
   - Định danh node không chứa dấu cách hoặc ký tự tiếng Việt có dấu.
3. Luôn bọc trong khối code ```mermaid ... ```.
