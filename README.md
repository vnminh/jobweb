# JobWeb — web việc làm demo cho JobUNICORN

Ứng dụng web gồm 3 vai trò, dựng trên đúng bộ dữ liệu CareerBuilder 2012 (window 7) và mô hình của báo cáo:

| Vai trò | Chức năng |
|---|---|
| **Người tìm việc** | Hồ sơ theo `users.tsv` + `user_history.tsv` (chức danh tự ánh xạ sang O*NET). Tìm kiếm/lọc việc (bang, thành phố, nhóm nghề, loại hình, cấp bậc), xem chi tiết kèm **độ phù hợp g_φ**, ứng tuyển, quản lý đơn. **Gợi ý nhanh** (không hội thoại) và **Trợ lý tìm việc** hội thoại (JobUNICORN R3). |
| **Nhà tuyển dụng** | Đăng/sửa/đóng tin theo `jobs.tsv` + thuộc tính có cấu trúc (nghề O*NET, kỹ năng, loại hình, cấp bậc, bằng cấp, số năm). Nút "Gợi ý từ nội dung" dùng bộ trích thuộc tính P3. Xem hồ sơ ứng viên kèm độ phù hợp, đổi trạng thái hồ sơ, **ứng viên gợi ý** theo embedding GNN. |
| **Quản trị viên** | Thống kê hệ thống, quản lý tài khoản (khoá/mở), quản lý tin (đóng/mở — loại khỏi gợi ý ngay), nhật ký hội thoại của trợ lý. |

## Khớp với bộ dữ liệu

| Bảng | Nguồn | Ghi chú |
|---|---|---|
| `seeker_profiles` | `users.tsv` (đã làm sạch ở P2) | City, State, Country, ZipCode, DegreeType, Major, GraduationDate, WorkHistoryCount, TotalYearsExperience, CurrentlyEmployed, ManagedOthers, ManagedHowMany; thêm `last_occ`, `seniority` (P3) và `world_idx` (hàng embedding của encoder) |
| `work_history` | `user_history.tsv` | Sequence, JobTitle + mã O*NET (bảng ánh xạ chức danh của P3) |
| `jobs`, `job_skills` | `jobs.tsv` (chỉ job canonical sau khi gộp trùng), P3 | Title, Description/Requirements (đã bỏ HTML), City, State, Country, Zip5, StartDate, EndDate + nghề, nhóm nghề, kỹ năng, loại hình, cấp bậc, bằng cấp, số năm, có nêu lương |
| `applications` | `apps.tsv` | ApplicationDate, ánh xạ sang job canonical, giữ vai trò A_cut5 (history/target) |
| `occupations`, `occ_groups`, `skills`, `states`, `cities`, `title_map` | node thuộc tính của đồ thị, O*NET 30.1 | giá trị các ô chọn = đúng các thuộc tính mà trợ lý hỏi |

Phần **không có trong bộ dữ liệu** (mở rộng của bản demo): tài khoản và đăng nhập, công ty (mỗi bang có một tài khoản nhà tuyển dụng sở hữu các tin của bang đó), trạng thái hồ sơ (`viewed/shortlisted/rejected/hired`), nhật ký hội thoại.

## Trợ lý hội thoại = mô hình của báo cáo

`backend/app/recsys/engine.py` nạp đúng `ConvEnv` (môi trường hội thoại), encoder GNN, mô hình phù hợp g_φ, truy hồi hai tầng FAISS và **policy R3** (`reports/post_p10_dqn/R3_belief_feats_pen08/policy.pt`) từ thư mục `jobunicorn/`. Điểm khác duy nhất so với thực nghiệm: user mô phỏng được thay bằng `LiveUser` — câu trả lời người dùng bấm trên web. Mỗi lượt:

1. người dùng trả lời → `env.step(hành động đang chờ)` cập nhật thuộc tính chấp nhận/từ chối, ràng buộc cứng, niềm tin `b = softmax(s / 1,758)`;
2. policy chọn hành động tiếp theo trong 10 câu hỏi (theo EIG) + 10 việc làm;
3. trình duyệt hiển thị câu hỏi (có/không, chọn nhiều, phân cấp nhóm nghề, khoảng cấp bậc, xác nhận bang) hoặc 10 gợi ý.

Việc đã ứng tuyển và tin đã đóng bị loại khỏi tập ứng viên.

**Thực thể tạo trên web** (tin mới, người dùng mới, hồ sơ mẫu khi kiểm tra) được tính embedding **bằng chính encoder P5 đã huấn luyện** (`backend/app/recsys/encoder.py`). Encoder R-GCN `d_gnn_aux.pt` chạy trên đồ thị con window 7, gắn thêm node mới bằng đúng các loại cạnh của P4 và cùng đặc trưng đầu vào của P5:

- **Tin mới:** embedding bge-small của "tiêu đề. mô tả. Requirements: yêu cầu"; các cạnh `is_occupation`, `requires_skill`, `located_in`, `job_seniority`, `has_type`, `requires_degree`.
- **Người dùng mới:** embedding chức danh đã làm với trọng số 0,7^(seq−1), cộng 8 đặc trưng số; các cạnh `held`, `has_degree`, `has_major`, `lives_in`, `user_seniority`, `applied`.

Kiểm chứng: lượt truyền cục bộ không có node mới tái tạo `node_emb_*` của window 7 với cosine 1,0000 (sai số tuyệt đối tối đa 0,002). Node của bộ dữ liệu giữ nguyên embedding đã xuất; chỉ hàng của thực thể web được ghi. Mỗi lần tạo hoặc sửa mất khoảng 2–3 giây.

Lần chạy đầu tiên, hệ thống mã hoá lại khoảng 96 nghìn chức danh của window 7 bằng bge-small trên CPU (khoảng 7 phút, lưu tại `backend/data/title_text_w7.npz`). Mô hình g_φ chỉ có đặc trưng cho người dùng/tin của bộ dữ liệu, nên với thực thể web, thành phần fit bằng 0 và độ phù hợp hiển thị "—".

## Tạo dữ liệu thử và kiểm tra mô hình

- **Tài khoản mới:** đăng ký người tìm việc → trang Hồ sơ có ô **"Điền hồ sơ mẫu…"** (5 hồ sơ: y tá Houston, kế toán Chicago, lập trình viên San Jose, nhân viên kho Atlanta, CSKH Phoenix) → Lưu → dùng Gợi ý nhanh / Trợ lý. Đăng ký nhà tuyển dụng → form đăng tin có **"Điền tin mẫu…"**.
- **Kiểm tra mô hình** (tab trong trang tin của nhà tuyển dụng): chọn số ứng viên gợi ý theo embedding, ứng viên đã nộp, và tự tạo **hồ sơ ứng viên mẫu** (không cần tài khoản). Với mỗi ứng viên, user mô phỏng theo luật của báo cáo đóng vai người **chỉ muốn đúng tin này**, trợ lý R3 chạy tối đa 15 lượt. Kết quả gồm tỷ lệ tìm ra, số lượt, số câu hỏi, hạng của tin trong 2.000 ứng viên ban đầu và toàn bộ hội thoại.
  Lưu ý: đây là bài toán một-đích giữa nhiều tin gần giống nhau, nên khó hơn giao thức đánh giá chính của báo cáo. Kiểm tra trên tin có thật trong bộ dữ liệu với đúng người đã nộp đơn: SR@15 khoảng 0,78.

## Chạy

Yêu cầu: môi trường conda `attt-env` của dự án `jobunicorn` (numpy, pandas, torch, faiss, scikit-learn), đã có `jobunicorn/data/processed` và `reports/post_p10_dqn/R3_belief_feats_pen08/policy.pt`; Node 18+ để build frontend.

```bash
# 1) cài gói web cho backend
~/anaconda3/envs/attt-env/bin/pip install -r backend/requirements.txt
# 2) tạo CSDL demo từ dữ liệu đã xử lý (~1 phút, ~550 MB)
cd backend && ~/anaconda3/envs/attt-env/bin/python -m scripts.import_dataset && cd ..
# 3) build frontend (một lần)
cd frontend && npm install && npm run build && cd ..
# 4) chạy (backend phục vụ luôn frontend đã build)
./run.sh            # mở http://localhost:8000
```

Engine gợi ý nạp trong nền khoảng 30–40 giây sau khi server khởi động (lần đầu thêm khoảng 7 phút để mã hoá chức danh) và cần khoảng 4–5 GB RAM. Đặt `JOBWEB_ENGINE=0` để chạy web không có mô hình.

Chế độ phát triển frontend: `cd frontend && npm run dev` (cổng 5173, proxy `/api` sang 8000).

### Tài khoản demo
| Vai trò | Email | Mật khẩu |
|---|---|---|
| Quản trị viên | `admin@jobweb.demo` | `admin123` |
| Nhà tuyển dụng | `recruiter.<bang>@jobweb.demo` (ví dụ `recruiter.tx@jobweb.demo`) | `demo123` |
| Người tìm việc | `user<UserID>@jobweb.demo` (mọi user window 7, ví dụ `user44@jobweb.demo`) | `demo123` |

Có thể tự đăng ký tài khoản người tìm việc hoặc nhà tuyển dụng mới.

## Cấu trúc
```
backend/
  app/main.py            FastAPI, nạp engine nền, phục vụ frontend/dist
  app/models.py          lược đồ CSDL (khớp các tệp TSV)
  app/recsys/engine.py   ConvEnv + policy R3 + LiveUser, mô phỏng kiểm tra mô hình
  app/recsys/encoder.py  encoder GNN P5 chạy cho node mới (tin/người dùng tạo trên web)
  app/samples.py         hồ sơ mẫu và tin mẫu
  app/routers/           auth, meta (taxonomy, gợi ý thuộc tính), jobs, seeker, assistant, recruiter, admin
  scripts/import_dataset.py   tạo CSDL từ jobunicorn/data
frontend/src/
  pages/seeker/          Jobs, JobDetail, Assistant, Applications, Profile
  pages/recruiter/       RecruiterJobs, JobForm, Applicants, Company
  pages/admin/           AdminDashboard, AdminUsers, AdminJobs, AdminConversations
```
