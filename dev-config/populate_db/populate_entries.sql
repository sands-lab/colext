INSERT INTO fl_testbed_logging.users(user_name, user_password) VALUES ('me', 'secure_password');

INSERT INTO fl_testbed_logging.jobs(user_id) VALUES (1);

INSERT INTO fl_testbed_logging.clients(client_number, job_id, device_id) VALUES(0, 1, 1)

INSERT INTO fl_testbed_logging.devices(device_name, device_code, status) VALUES ('JetsonAGXOrin', 'jao1', 'ACTIVE');
INSERT INTO fl_testbed_logging.devices(device_name, device_code, status) VALUES ('JetsonOrinNano', 'jon1', 'ACTIVE');
INSERT INTO fl_testbed_logging.devices(device_name, device_code, status) VALUES ('JetsonOrinNano', 'jon2', 'ACTIVE');
INSERT INTO fl_testbed_logging.devices(device_name, device_code, status) VALUES ('JetsonOrinNano', 'jon3', 'ACTIVE');
INSERT INTO fl_testbed_logging.devices(device_name, device_code, status) VALUES ('LattePandaDelta3', 'lp1', 'ACTIVE');
INSERT INTO fl_testbed_logging.devices(device_name, device_code, status) VALUES ('LattePandaDelta3', 'lp3', 'ACTIVE');
INSERT INTO fl_testbed_logging.devices(device_name, device_code, status) VALUES ('LattePandaDelta3', 'lp4', 'ACTIVE');
INSERT INTO fl_testbed_logging.devices(device_name, device_code, status) VALUES ('LattePandaDelta3', 'lp5', 'ACTIVE');
INSERT INTO fl_testbed_logging.devices(device_name, device_code, status) VALUES ('LattePandaDelta3', 'lp6', 'ACTIVE');
INSERT INTO fl_testbed_logging.devices(device_name, device_code, status) VALUES ('OrangePi5B', 'op1', 'ACTIVE');
INSERT INTO fl_testbed_logging.devices(device_name, device_code, status) VALUES ('OrangePi5B', 'op2', 'ACTIVE');
INSERT INTO fl_testbed_logging.devices(device_name, device_code, status) VALUES ('OrangePi5B', 'op3', 'ACTIVE');
INSERT INTO fl_testbed_logging.devices(device_name, device_code, status) VALUES ('OrangePi5B', 'op4', 'ACTIVE');
INSERT INTO fl_testbed_logging.devices(device_name, device_code, status) VALUES ('OrangePi5B', 'op5', 'ACTIVE');
INSERT INTO fl_testbed_logging.devices(device_name, device_code, status) VALUES ('OrangePi5B', 'op6', 'ACTIVE');
INSERT INTO fl_testbed_logging.devices(device_name, device_code, status) VALUES ('JetsonNano', 'jn1', 'ACTIVE');