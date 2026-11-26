# JobWeb — sàn việc làm demo cho JobUNICORN

Ứng dụng web 3 vai trò dựng trên bộ dữ liệu CareerBuilder 2012 (window 7). Trợ lý tìm việc hội thoại chạy mô hình JobUNICORN (policy R3, encoder R-GCN, mô hình phù hợp g_φ).

| Vai trò | Chức năng |
|---|---|
| **Người tìm việc** | Tạo và quản lý hồ sơ; tìm kiếm, lọc việc (bang, thành phố, nhóm nghề, loại hình, cấp bậc); xem chi tiết kèm độ phù hợp; ứng tuyển; **Gợi ý nhanh** và **Trợ lý tìm việc** hội thoại. |
| **Nhà tuyển dụng** | Đăng, sửa, đóng tin; xem hồ sơ ứng tuyển kèm độ phù hợp; ứng viên tiềm năng; **Mô phỏng tiếp cận** (trợ lý có tìm ra tin của bạn cho đúng ứng viên không). |
| **Quản trị viên** | Thống kê hệ thống, quản lý tài khoản và tin đăng, nhật ký hội thoại của trợ lý. |

---

## 1. Chạy nhanh bằng Docker (Windows, macOS, Linux)

Toàn bộ dữ liệu, checkpoint mô hình và cơ sở dữ liệu đã được đóng sẵn trong 3 image trên Docker Hub, nên không cần tải dữ liệu riêng:

| Image | Nội dung |
|---|---|
| [`leevox/jobweb-db`](https://hub.docker.com/r/leevox/jobweb-db) | PostgreSQL 16 đã nạp sẵn CSDL demo của window 7: 49.735 ứng viên, 111.523 tin tuyển dụng, 181.350 đơn ứng tuyển |
| [`leevox/jobweb-backend`](https://hub.docker.com/r/leevox/jobweb-backend) | FastAPI + mô hình JobUNICORN, dữ liệu đã xử lý (≈ 2,1 GB), checkpoint, mô hình văn bản bge-small |
| [`leevox/jobweb-frontend`](https://hub.docker.com/r/leevox/jobweb-frontend) | Giao diện React, phục vụ bằng nginx (chuyển tiếp `/api` sang backend) |

**Yêu cầu**
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/macOS) hoặc Docker Engine + Compose v2 (Linux).
- Cấp cho Docker **ít nhất 6 GB RAM** (Docker Desktop → Settings → Resources). Backend cần khoảng 4–5 GB khi nạp mô hình.
- Khoảng 8 GB dung lượng đĩa trống.

**Chạy**

```bash
git clone https://github.com/vnminh/jobweb.git
cd jobweb
docker compose pull        # tải 3 image (lần đầu khoảng 3–4 GB)
docker compose up -d       # khởi động db, backend, frontend
```

Mở **http://localhost:8080**. Web dùng được ngay. Mô hình gợi ý nạp trong nền khoảng 30–60 giây; xem trạng thái tại http://localhost:8080/api/health (`"engine": true` là đã sẵn sàng).

| Lệnh | Tác dụng |
|---|---|
| `docker compose logs -f backend` | xem log backend |
| `docker compose down` | dừng (giữ dữ liệu đã tạo trên web) |
| `docker compose down -v` | dừng và **xoá** dữ liệu, lần sau quay về CSDL gốc |
| `WEB_PORT=9000 docker compose up -d` | đổi cổng web (mặc định 8080; API ở 8000, đổi bằng `API_PORT`) |
| `JOBWEB_ENGINE=0 docker compose up -d` | chạy web không nạp mô hình (máy ít RAM) |

Trên máy Apple Silicon (M1/M2/M3…), image chạy qua giả lập amd64 (Rosetta) của Docker Desktop. Hãy bật *Settings → General → Use Rosetta for x86_64/amd64 emulation*.

### Tài khoản demo

| Vai trò | Email | Mật khẩu |
|---|---|---|
| Quản trị viên | `admin@jobweb.demo` | `admin123` |
| Nhà tuyển dụng | `recruiter.<bang>@jobweb.demo` (ví dụ `recruiter.tx@jobweb.demo`) | `demo123` |
| Người tìm việc | `user<UserID>@jobweb.demo` (mọi user của window 7, ví dụ `user44@jobweb.demo`) | `demo123` |

Có thể tự đăng ký tài khoản người tìm việc hoặc nhà tuyển dụng mới. Trang Hồ sơ có ô **"Điền hồ sơ mẫu…"**, form đăng tin có **"Điền tin mẫu…"** để tạo nhanh dữ liệu thử.

---

## 2. Mô hình và dữ liệu

### Checkpoint (có sẵn trong repo, thư mục `jobunicorn/`)

| File | Mô hình |
|---|---|
| `jobunicorn/reports/post_p10_dqn/R3_belief_feats_pen08/policy.pt` | Policy hội thoại R3 (R-GCN + Double/Dueling DQN) |
| `jobunicorn/reports/p5_encoder/d_gnn_aux.pt` | Encoder đồ thị dị thể R-GCN (BPR + loss phụ), tính embedding cho tin/người dùng mới |
| `jobunicorn/data/processed/fit/g_phi.pkl` | Mô hình phù hợp g_φ (Gradient Boosting) |

`jobunicorn/src` là mã nguồn JobUNICORN (môi trường hội thoại, policy, truy hồi FAISS hai tầng, encoder). `jobunicorn/configs` là cấu hình của mô hình cuối.

### Dữ liệu đã xử lý (≈ 2,1 GB, nằm trong image backend)

Danh sách file ở `docker/data_files.txt`: embedding node của đồ thị, đồ thị dị thể `hetero.pt`, ma trận thuộc tính của tin, embedding văn bản, bảng người dùng/tin/đơn ứng tuyển đã làm sạch. Để chép dữ liệu ra máy (ví dụ để chạy không dùng Docker):

```bash
docker create --name jw-data leevox/jobweb-backend:latest
docker cp jw-data:/app/jobunicorn/data/. ./jobunicorn/data/
docker cp jw-data:/app/cache/. ./backend/data/
docker rm jw-data
```

Dữ liệu gốc là bộ [Job Recommendation Challenge](https://www.kaggle.com/c/job-recommendation) (CareerBuilder, Kaggle).

---

## 3. Chạy không dùng Docker (phát triển)

Cần Python 3.12 và Node 18+.

```bash
# 1) dữ liệu: chép từ image như mục 2
# 2) thư viện Python (torch bản CPU)
pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
pip install -r docker/requirements-backend.txt
# 3) CSDL: dùng PostgreSQL trong image db
docker compose up -d db
export DATABASE_URL=postgresql+psycopg://jobweb:jobweb@localhost:5432/jobweb
```

Muốn truy cập cổng 5432 từ máy, thêm `ports: ["5432:5432"]` cho service `db` trong `docker-compose.yml`. Không đặt `DATABASE_URL` thì backend dùng SQLite tại `backend/data/jobweb.db`. File này được tạo bằng `python -m scripts.import_dataset` và cần toàn bộ dữ liệu đã xử lý của JobUNICORN.

```bash
# 4) backend (cổng 8000)
cd backend && python -m uvicorn app.main:app --port 8000
# 5) frontend (cổng 5173, proxy /api sang 8000)
cd frontend && npm install && npm run dev
```

Biến môi trường: `DATABASE_URL`, `JOBUNICORN_REPO` (mặc định `./jobunicorn`), `JOBUNICORN_DATA`, `JOBWEB_CACHE`, `JOBWEB_SECRET`, `JOBWEB_ENGINE=0` (tắt mô hình).

### Build và đẩy lại image (người bảo trì)

```bash
docker/collect_data.sh /path/to/jobunicorn/data backend/data/title_text_w7.npz   # chuẩn bị docker/assets
docker compose build backend frontend
docker/build_db_dump.sh /path/to/jobunicorn/data                                  # tạo docker/assets/jobweb.dump
docker compose build db
docker compose push
```

---

## 4. Trợ lý hội thoại hoạt động thế nào

`backend/app/recsys/engine.py` nạp môi trường hội thoại `ConvEnv`, encoder GNN, mô hình phù hợp g_φ, truy hồi hai tầng FAISS và policy R3. Người dùng thật thay cho user mô phỏng (`LiveUser`). Mỗi lượt:

1. Người dùng trả lời. `env.step` cập nhật thuộc tính chấp nhận/từ chối, ràng buộc cứng và niềm tin `b = softmax(s / 1,758)`.
2. Policy chọn hành động tiếp theo: hỏi một thuộc tính hoặc gợi ý 10 việc làm.
3. Trình duyệt hiển thị câu hỏi (có/không, chọn nhiều, nhóm nghề phân cấp, khoảng cấp bậc, xác nhận bang) hoặc danh sách gợi ý.

Việc đã ứng tuyển và tin đã đóng bị loại khỏi tập ứng viên.

**Tin và người dùng tạo trên web** được tính embedding bằng chính encoder R-GCN đã huấn luyện (`backend/app/recsys/encoder.py`). Encoder chạy trên đồ thị con window 7, gắn node mới bằng đúng các loại cạnh và đặc trưng đầu vào như lúc huấn luyện:

- **Tin mới:** embedding bge-small của tiêu đề, mô tả và yêu cầu; các cạnh `is_occupation`, `requires_skill`, `located_in`, `job_seniority`, `has_type`, `requires_degree`.
- **Người dùng mới:** embedding các chức danh đã làm (trọng số 0,7^(seq−1)) cộng 8 đặc trưng số; các cạnh `held`, `has_degree`, `has_major`, `lives_in`, `user_seniority`, `applied`.

Mô hình g_φ chỉ có đặc trưng cho người dùng/tin của bộ dữ liệu. Vì vậy, với thực thể tạo trên web, thành phần fit bằng 0 và độ phù hợp hiển thị "—".

### Khớp với bộ dữ liệu

| Bảng | Nguồn |
|---|---|
| `seeker_profiles`, `work_history` | `users.tsv`, `user_history.tsv` (chức danh ánh xạ sang O*NET) |
| `jobs`, `job_skills` | `jobs.tsv` (job canonical sau khi gộp trùng) + thuộc tính trích xuất (nghề, kỹ năng, loại hình, cấp bậc, bằng cấp, số năm) |
| `applications` | `apps.tsv` |
| `occupations`, `occ_groups`, `skills`, `states`, `cities`, `title_map` | node thuộc tính của đồ thị, O*NET 30.1 |

Phần không có trong bộ dữ liệu (mở rộng của bản demo): tài khoản, công ty (mỗi bang một tài khoản nhà tuyển dụng sở hữu các tin của bang đó), trạng thái hồ sơ, nhật ký hội thoại.

---

## 5. Cấu trúc

```
docker-compose.yml       3 service: db (PostgreSQL), backend (FastAPI + mô hình), frontend (nginx)
docker/                  Dockerfile của từng image, nginx.conf, script chuẩn bị dữ liệu và CSDL
backend/
  app/main.py            FastAPI, nạp mô hình trong nền
  app/models.py          lược đồ CSDL
  app/recsys/engine.py   ConvEnv + policy R3 + LiveUser, mô phỏng tiếp cận
  app/recsys/encoder.py  encoder GNN cho node mới
  app/routers/           auth, meta, jobs, seeker, assistant, recruiter, admin
  scripts/import_dataset.py   tạo CSDL từ dữ liệu đã xử lý
frontend/src/            giao diện React (seeker, recruiter, admin)
jobunicorn/              mã nguồn, cấu hình và checkpoint của mô hình
```
