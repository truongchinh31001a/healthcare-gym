# Bộ quy tắc mục tiêu wellness v1

Chạy độc lập với LLM, chỉ ghi mục tiêu cân nặng do người dùng chủ động phê duyệt. Không sinh menu,
đơn thuốc, cường độ tập hoặc xác nhận y tế. `automatic_plan_authorized` và `medical_clearance` luôn false.

Cần hồ sơ người trưởng thành tự khai báo, một nguồn weight reviewed/đủ hỗ trợ xu hướng/còn mới; nhiều nguồn
phải chọn stream cụ thể. Unknown của pregnancy/ăn uống/giới hạn bác sĩ/triệu chứng → cần bổ sung;
positive → cần chuyên gia. Người dưới 20 tuổi cần đánh giá riêng; không áp adult BMI cutoffs cho họ.
Với 20+, current/target BMI dưới 18,5 hoặc tốc độ yêu cầu lớn hơn 1 kg/tuần → cần chuyên gia.
Mục tiêu tăng cân cũng cần đánh giá riêng. Đây là giới hạn hỗ trợ của MVP, không phải khuyến nghị cá nhân.

Mốc BMI tham khảo [CDC dành cho tuổi 20+](https://www.cdc.gov/bmi/adult-calculator/bmi-categories.html).
Mốc tốc độ giảm cân tổng quát tham khảo [NHS](https://www.nhs.uk/live-well/healthy-weight/managing-your-weight/tips-to-help-you-lose-weight/).
Các câu hỏi/rules chưa được thẩm định như một công cụ triage, không chứng minh người dùng không có nguy cơ.
Kết quả active chỉ nghĩa mục tiêu đã được ghi nhận qua rule tại thời điểm duyệt, không phải clearance.
Thay hồ sơ/context/số đo/consent làm active goal cần kiểm tra lại; thay target cần explicit approval + reason/version.
