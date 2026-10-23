-- Idempotent: รันซ้ำได้ ไม่พังและไม่ลบข้อมูลเดิม

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS audit;

-- Audit: 1 แถวต่อการรัน pipeline 1 ครั้ง
CREATE TABLE IF NOT EXISTS audit.pipeline_runs (
    run_id        BIGSERIAL PRIMARY KEY,
    pipeline      VARCHAR(50)  NOT NULL,
    source_file   VARCHAR(255),
    status        VARCHAR(20)  NOT NULL
                  CHECK (status IN ('running', 'success', 'failed', 'skipped')),
    started_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    rows_read     INT,
    rows_inserted INT,
    rows_updated  INT,
    rows_rejected INT DEFAULT 0,
    error_message TEXT
);

-- Raw: เก็บข้อมูลดิบทุกแถวตามต้นฉบับ (ยังไม่ clean)
-- grain = 1 บรรทัดใน invoice, line_id = '<invoice_no>-<line_no>'
CREATE TABLE IF NOT EXISTS raw.online_retail (
    line_id      VARCHAR(30) PRIMARY KEY,
    invoice_no   VARCHAR(20) NOT NULL,
    line_no      INT         NOT NULL,
    stock_code   VARCHAR(20) NOT NULL,
    description  VARCHAR(255),
    quantity     INT,
    invoice_date TIMESTAMP,
    unit_price   NUMERIC,
    customer_id  INT,
    country      VARCHAR(100),
    source_file  VARCHAR(255),
    run_id       BIGINT REFERENCES audit.pipeline_runs(run_id),
    loaded_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Audit: แถวที่ไม่ผ่าน validation (ใช้ใน Phase 2)
CREATE TABLE IF NOT EXISTS audit.rejected_rows (
    rejected_id BIGSERIAL PRIMARY KEY,
    run_id      BIGINT NOT NULL REFERENCES audit.pipeline_runs(run_id),
    line_id     VARCHAR(30),
    reason      TEXT   NOT NULL,
    record      JSONB,
    rejected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
