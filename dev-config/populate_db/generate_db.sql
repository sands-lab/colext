CREATE SCHEMA fl_testbed_logging;
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE fl_testbed_logging.users (
    user_id serial primary key,
    user_name varchar(100),
    user_password varchar(255)
);

CREATE TABLE fl_testbed_logging.jobs (
    job_id SERIAL PRIMARY KEY,
    start_time timestamp with time zone,
    end_time timestamp with time zone,
    config JSONB,
    model bytea,
    user_id INT REFERENCES fl_testbed_logging.users(user_id)
);

CREATE TABLE fl_testbed_logging.rounds (
    round_id serial primary key,
    round_number integer,
    start_time timestamp with time zone,
    end_time timestamp with time zone,
    accuracy decimal,
    fit_eval varchar(50),
    job_id INT REFERENCES fl_testbed_logging.jobs(job_id)
);

CREATE TABLE fl_testbed_logging.devices (
    device_id serial primary key,
    device_name varchar(100),
    device_code varchar(100),
    OS_version varchar(100),
    status varchar(50)
);

CREATE TABLE fl_testbed_logging.clients (
		client_id SERIAL PRIMARY KEY,
		client_number integer,
		job_id INT REFERENCES fl_testbed_logging.jobs(job_id),
		device_id INT REFERENCES fl_testbed_logging.devices(device_id)
);

CREATE TABLE fl_testbed_logging.clients_in_rounds (
    cir_id serial primary key,
    client_id INT REFERENCES fl_testbed_logging.clients(client_id),
    round_id INT REFERENCES fl_testbed_logging.rounds(round_id),
		client_state varchar(50)
);

CREATE TABLE fl_testbed_logging.epochs (
    epoch_id serial primary key,
    epoch_number integer,
    start_time timestamp with time zone,
    end_time timestamp with time zone,
    cir_id INT REFERENCES fl_testbed_logging.clients_in_rounds(cir_id)
);

CREATE TABLE fl_testbed_logging.batches (
    batch_id serial primary key,
    batch_number integer,
    start_time timestamp with time zone,
    end_time timestamp with time zone,
    loss decimal,
    frwd_pass_time timestamp with time zone,
    bkwd_pass_time timestamp with time zone,
    opt_step_time timestamp with time zone,
    epoch_id INT REFERENCES fl_testbed_logging.epochs(epoch_id)
);

CREATE TABLE fl_testbed_logging.device_measurements (
    time timestamp with time zone NOT NULL,
    cpu_util decimal,
    mem_util decimal,
    gpu_util decimal,
    battery_state decimal,
    power_consumption decimal,
		gpu_info jsonb,
		cpu_info jsonb,
    client_id INT REFERENCES fl_testbed_logging.clients(client_id)
);

SELECT create_hypertable('fl_testbed_logging.device_measurements', 'time', if_not_exists => TRUE, create_default_indexes => TRUE);

CREATE TABLE fl_testbed_logging.monsoon_measurements (
    time timestamp with time zone NOT NULL,
    voltage_val decimal,
    current_val decimal,
    power_val decimal,
    client_id INT REFERENCES fl_testbed_logging.clients(client_id)
);

SELECT create_hypertable('fl_testbed_logging.monsoon_measurements', 'time', if_not_exists => TRUE, create_default_indexes => TRUE);