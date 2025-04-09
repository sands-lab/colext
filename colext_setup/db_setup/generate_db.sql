CREATE SCHEMA fl_testbed_logging;
SET search_path TO fl_testbed_logging;
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    user_name VARCHAR(100) UNIQUE,
    user_password VARCHAR(255)
);

CREATE TABLE projects (
    project_id SERIAL PRIMARY KEY,
    project_name VARCHAR(100) UNIQUE,
    is_active BOOLEAN,
);

CREATE TABLE project_user (
    project_id INT REFERENCES projects(project_id),
    user_id INT REFERENCES users(user_id),
    PRIMARY KEY (project_id, user_id)
);

CREATE TABLE jobs (
    job_id SERIAL PRIMARY KEY,
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    config JSONB,
    model bytea,
    user_id INT REFERENCES users(user_id),
    project_id INT REFERENCES projects(project_id)
);

CREATE TABLE rounds (
    round_id SERIAL PRIMARY KEY,
    round_number INTEGER,
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    dist_accuracy DECIMAL,
    srv_accuracy DECIMAL,
    stage VARCHAR(50),
    job_id INT REFERENCES jobs(job_id)
);

CREATE TABLE devices (
    device_id SERIAL PRIMARY KEY,
    device_name VARCHAR(100),
    device_code VARCHAR(100) UNIQUE,
    OS_version VARCHAR(100),
    status VARCHAR(50)
);

CREATE TABLE clients (
    client_id SERIAL PRIMARY KEY,
    client_number INTEGER,
    job_id INT REFERENCES jobs(job_id),
    device_id INT REFERENCES devices(device_id)
);

CREATE TABLE clients_in_round (
    cir_id SERIAL PRIMARY KEY,
    client_id INT REFERENCES clients(client_id),
    round_id INT REFERENCES rounds(round_id),
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    loss DECIMAL,
    num_examples INT,
    accuracy DECIMAL,
    client_state VARCHAR(50)
);

-- Associated with a round stage
CREATE TABLE server_round_metrics (
    round_id INT PRIMARY KEY REFERENCES rounds(round_id),
    configure_time_start TIMESTAMP WITH TIME ZONE,
    configure_time_end TIMESTAMP WITH TIME ZONE,
    aggregate_time_start TIMESTAMP WITH TIME ZONE,
    aggregate_time_end TIMESTAMP WITH TIME ZONE,
    eval_time_start TIMESTAMP WITH TIME ZONE,
    eval_time_end TIMESTAMP WITH TIME ZONE
);

CREATE TABLE epochs (
    epoch_id SERIAL PRIMARY KEY,
    epoch_number INTEGER,
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    cir_id INT REFERENCES clients_in_round(cir_id)
);

CREATE TABLE batches (
    batch_id SERIAL PRIMARY KEY,
    batch_number INTEGER,
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    loss DECIMAL,
    frwd_pass_time TIMESTAMP WITH TIME ZONE,
    bkwd_pass_time TIMESTAMP WITH TIME ZONE,
    opt_step_time TIMESTAMP WITH TIME ZONE,
    epoch_id INT REFERENCES epochs(epoch_id)
);

CREATE TABLE device_measurements (
    time TIMESTAMP WITH TIME ZONE NOT NULL,
    cpu_util DECIMAL,
    mem_util DECIMAL,
    gpu_util DECIMAL,
    battery_state DECIMAL,
    power_consumption DECIMAL,

    n_bytes_sent DECIMAL,
    n_bytes_rcvd DECIMAL,
    net_usage_out DECIMAL,
    net_usage_in DECIMAL,

    gpu_info jsonb,
    cpu_info jsonb,
    client_id INT REFERENCES clients(client_id)
);

SELECT create_hypertable('device_measurements', 'time', if_not_exists => TRUE, create_default_indexes => TRUE);

CREATE TABLE monsoon_measurements (
    time TIMESTAMP WITH TIME ZONE NOT NULL,
    voltage_val DECIMAL,
    current_val DECIMAL,
    power_val DECIMAL,
    client_id INT REFERENCES clients(client_id)
);

SELECT create_hypertable('monsoon_measurements', 'time', if_not_exists => TRUE, create_default_indexes => TRUE);

-- Add security
CREATE ROLE colext_user;
ALTER ROLE colext_user SET search_path TO fl_testbed_logging;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA fl_testbed_logging TO colext_user;

ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE rounds ENABLE ROW LEVEL SECURITY;
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE clients_in_round ENABLE ROW LEVEL SECURITY;
ALTER TABLE epochs ENABLE ROW LEVEL SECURITY;
ALTER TABLE batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE device_measurements ENABLE ROW LEVEL SECURITY;
ALTER TABLE monsoon_measurements ENABLE ROW LEVEL SECURITY;
ALTER TABLE server_round_metrics ENABLE ROW LEVEL SECURITY;

-- CREATE POLICY pc_jobs ON jobs
CREATE POLICY p_jobs ON jobs
    USING (project_id IN (SELECT DISTINCT project_id FROM projects WHERE is_active = TRUE));
    -- USING (project_id IN (SELECT DISTINCT project_id FROM project_users JOIN users USING(user_id) WHERE user_name = current_user));
CREATE POLICY p_rounds ON rounds USING (job_id IN (SELECT DISTINCT job_id FROM jobs));
CREATE POLICY p_clients ON clients USING (job_id IN (SELECT DISTINCT job_id FROM jobs));
CREATE POLICY p_clients_in_round ON clients_in_round USING (client_id IN (SELECT DISTINCT client_id FROM clients));
CREATE POLICY p_epochs ON epochs USING (cir_id IN (SELECT DISTINCT cir_id FROM clients_in_round));
CREATE POLICY p_batches ON batches USING (cir_id IN (SELECT DISTINCT cir_id FROM clients_in_round));
CREATE POLICY p_device_measurements ON device_measurements USING (client_id IN (SELECT DISTINCT client_id FROM clients));
CREATE POLICY p_monsoon_measurements ON monsoon_measurements USING (client_id IN (SELECT DISTINCT client_id FROM clients));
CREATE POLICY p_server_round_metrics ON server_round_metrics USING (round_id IN (SELECT DISTINCT round_id FROM rounds));

GRANT USAGE ON SEQUENCE
    jobs_job_id_seq,
    rounds_round_id_seq,
    clients_client_id_seq,
    clients_in_round_cir_id_seq
    TO colext_user;