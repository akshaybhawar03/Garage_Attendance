CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE companies (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  company_code VARCHAR(20) UNIQUE NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE admins (
  id SERIAL PRIMARY KEY,
  company_id INT REFERENCES companies(id),
  name VARCHAR(100) NOT NULL,
  email VARCHAR(100) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE employees (
  id SERIAL PRIMARY KEY,
  company_id INT REFERENCES companies(id),
  name VARCHAR(100) NOT NULL,
  phone VARCHAR(15),
  monthly_salary DECIMAL(10,2) NOT NULL,
  joining_date DATE NOT NULL,
  profile_photo_url TEXT,
  status VARCHAR(10) DEFAULT 'active',
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE face_vectors (
  id SERIAL PRIMARY KEY,
  employee_id INT REFERENCES employees(id) ON DELETE CASCADE,
  face_vector vector(512) NOT NULL,
  angle_type VARCHAR(10) NOT NULL,
  registered_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE attendance (
  id SERIAL PRIMARY KEY,
  employee_id INT REFERENCES employees(id),
  company_id INT REFERENCES companies(id),
  attendance_date DATE NOT NULL,
  check_in TIMESTAMP,
  check_out TIMESTAMP,
  status VARCHAR(10) DEFAULT 'absent',
  match_score DECIMAL(5,4),
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(employee_id, attendance_date)
);

CREATE TABLE salary_records (
  id SERIAL PRIMARY KEY,
  employee_id INT REFERENCES employees(id),
  month INT NOT NULL,
  year INT NOT NULL,
  working_days INT NOT NULL,
  present_days INT NOT NULL DEFAULT 0,
  late_days INT NOT NULL DEFAULT 0,
  absent_days INT NOT NULL DEFAULT 0,
  monthly_salary DECIMAL(10,2) NOT NULL,
  per_day_salary DECIMAL(10,2) NOT NULL,
  deduction_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
  net_pay DECIMAL(10,2) NOT NULL,
  generated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(employee_id, month, year)
);

CREATE TABLE settings (
  id SERIAL PRIMARY KEY,
  company_id INT REFERENCES companies(id) UNIQUE,
  work_start_time TIME DEFAULT '09:00:00',
  work_end_time TIME DEFAULT '18:00:00',
  late_threshold_minutes INT DEFAULT 15,
  working_days_per_week INT DEFAULT 6,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_attendance_date ON attendance(attendance_date);
CREATE INDEX idx_attendance_employee ON attendance(employee_id);
CREATE INDEX idx_attendance_company ON attendance(company_id);
CREATE INDEX idx_face_vectors_employee ON face_vectors(employee_id);
CREATE INDEX idx_face_angle ON face_vectors(employee_id, angle_type);
CREATE INDEX idx_employees_company ON employees(company_id);

CREATE OR REPLACE FUNCTION find_matching_employee(
  query_vector vector(512),
  threshold FLOAT DEFAULT 0.65,
  p_company_id INT DEFAULT 1
) RETURNS TABLE(
  employee_id INT,
  employee_name VARCHAR,
  similarity FLOAT,
  angle_type VARCHAR
) AS $$
BEGIN
  RETURN QUERY
  SELECT e.id, e.name,
    (1 - (fv.face_vector <=> query_vector))::FLOAT AS similarity,
    fv.angle_type::VARCHAR
  FROM face_vectors fv
  JOIN employees e ON e.id = fv.employee_id
  WHERE e.company_id = p_company_id
    AND e.status = 'active'
    AND 1 - (fv.face_vector <=> query_vector) >= threshold
  ORDER BY similarity DESC
  LIMIT 1;
END;
$$ LANGUAGE plpgsql;

INSERT INTO companies(name, company_code)
  VALUES ('Test Garage', 'GARAGE2024');

INSERT INTO admins(company_id, name, email, password_hash)
  VALUES (1, 'Garage Owner', 'owner@garage.com',
  '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMqJqhcan2rosZ2I');

INSERT INTO settings(company_id) VALUES (1);
