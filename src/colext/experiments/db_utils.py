import logging
import psycopg
from psycopg.rows import dict_row
log = logging.getLogger(__name__)

class DBUtils:
    def __init__(self) -> None:
        self.DB_CONNECTION = self.create_db_connection()

    def create_db_connection(self):
        DB_CONNECTION_INFO = "host=flserver dbname=fl_testbed_db_copy user=faustiar_test_user password=faustiar_test_user"
        return psycopg.connect(DB_CONNECTION_INFO)
    
    def create_job(self) -> str:
        cursor = self.DB_CONNECTION.cursor()
        sql = "INSERT INTO fl_testbed_logging.jobs(start_time, user_id) VALUES (CURRENT_TIMESTAMP, 1) returning job_id"
        cursor.execute(sql)
        JOB_ID = cursor.fetchone()[0]

        self.DB_CONNECTION.commit()
        return JOB_ID
    
    def get_current_available_clients(self, device_types: tuple) -> str:
        cursor = self.DB_CONNECTION.cursor()
        sql = "SELECT device_id, device_code AS hostname, device_name FROM fl_testbed_logging.devices WHERE device_name = ANY(%s) AND status = %s"
        data = (device_types, 'ACTIVE')
        cursor.execute(sql, data)
        db_devices = cursor.fetchall()

        return db_devices
    
    def register_clients(self, job_id, clients_to_register):
        cursor = self.DB_CONNECTION.cursor(row_factory=dict_row)
        sql = "INSERT INTO fl_testbed_logging.clients (client_number, job_id, device_id) values (%s, %s, %s)"
        cursor.executemany(sql, clients_to_register)

        sql = "SELECT client_number,client_id FROM fl_testbed_logging.clients WHERE job_id = %s"
        data = (job_id,)
        cursor.execute(sql, data)
        registered_clients = cursor.fetchall()

        self.DB_CONNECTION.commit()
        return registered_clients
    
    def commit_changes(self):
        self.DB_CONNECTION.commit()

    def get_metrics(self, job_id, metric_writer):
        cursor = self.DB_CONNECTION.cursor()
        sql = """
                COPY 
                (SELECT client_number, time, cpu_util, mem_util, gpu_util, power_consumption
                    FROM clients
                    JOIN device_measurements USING (client_id)
                    JOIN jobs USING (job_id)
                    JOIN devices USING(device_id)
                    WHERE jobs.job_id = %s) 
                TO STDOUT WITH (FORMAT CSV, HEADER)
               """
        data = (job_id,)
        with cursor.copy(sql, data) as copy:
            for data in copy:
                metric_writer.write(data)