CREATE SCHEMA fl_testbed_logging;
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE fl_testbed_logging.users (
    user_id SERIAL PRIMARY KEY,
    user_name VARCHAR(100),
    user_password VARCHAR(255)
);

CREATE TABLE fl_testbed_logging.jobs (
    job_id SERIAL PRIMARY KEY,
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    config JSONB,
    model bytea,
    user_id INT REFERENCES fl_testbed_logging.users(user_id)
);

CREATE TABLE fl_testbed_logging.rounds (
    round_id SERIAL PRIMARY KEY,
    round_number INTEGER,
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    dist_accuracy DECIMAL,
    srv_accuracy DECIMAL,
    stage VARCHAR(50),
    job_id INT REFERENCES fl_testbed_logging.jobs(job_id)
);

CREATE TABLE fl_testbed_logging.devices (
    device_id SERIAL PRIMARY KEY,
    device_name VARCHAR(100),
    device_code VARCHAR(100) UNIQUE,
    OS_version VARCHAR(100),
    status VARCHAR(50)
);

CREATE TABLE fl_testbed_logging.clients (
		client_id SERIAL PRIMARY KEY,
		client_number INTEGER,
		job_id INT REFERENCES fl_testbed_logging.jobs(job_id),
		device_id INT REFERENCES fl_testbed_logging.devices(device_id)
);

CREATE TABLE fl_testbed_logging.clients_in_round (
    cir_id SERIAL PRIMARY KEY,
    client_id INT REFERENCES fl_testbed_logging.clients(client_id),
    round_id INT REFERENCES fl_testbed_logging.rounds(round_id),
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    loss DECIMAL,
    num_examples INT,
    accuracy DECIMAL,
    client_state VARCHAR(50)
);

CREATE TABLE fl_testbed_logging.epochs (
    epoch_id SERIAL PRIMARY KEY,
    epoch_number INTEGER,
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    cir_id INT REFERENCES fl_testbed_logging.clients_in_round(cir_id)
);

CREATE TABLE fl_testbed_logging.batches (
    batch_id SERIAL PRIMARY KEY,
    batch_number INTEGER,
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    loss DECIMAL,
    frwd_pass_time TIMESTAMP WITH TIME ZONE,
    bkwd_pass_time TIMESTAMP WITH TIME ZONE,
    opt_step_time TIMESTAMP WITH TIME ZONE,
    epoch_id INT REFERENCES fl_testbed_logging.epochs(epoch_id)
);

CREATE TABLE fl_testbed_logging.device_measurements (
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
    client_id INT REFERENCES fl_testbed_logging.clients(client_id)
);

SELECT create_hypertable('fl_testbed_logging.device_measurements', 'time', if_not_exists => TRUE, create_default_indexes => TRUE);

CREATE TABLE fl_testbed_logging.monsoon_measurements (
    time TIMESTAMP WITH TIME ZONE NOT NULL,
    voltage_val DECIMAL,
    current_val DECIMAL,
    power_val DECIMAL,
    client_id INT REFERENCES fl_testbed_logging.clients(client_id)
);

SELECT create_hypertable('fl_testbed_logging.monsoon_measurements', 'time', if_not_exists => TRUE, create_default_indexes => TRUE);