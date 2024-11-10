from typing import Tuple, BinaryIO
import psycopg

class DBUtils:
    def __init__(self) -> None:
        self.DB_CONNECTION = self.create_db_connection()

    def create_db_connection(self):
        # Connection string is read from env variable pointing to pgpassfile
        return psycopg.connect(dbname="colext_db", autocommit=True)

    def project_exists(self, project_name) -> bool:
        try:
            self.get_project_id(project_name)
            return True
        except ProjectNotFoundException:
            return False

    def get_project_id(self, project_name) -> int:
        cursor = self.DB_CONNECTION.cursor()
        sql = "SELECT project_id FROM projects WHERE project_name = %s"
        data = (project_name,)
        cursor.execute(sql, data)
        record = cursor.fetchone()
        cursor.close()

        if record is None:
            raise ProjectNotFoundException

        return record[0]

    # Passing config as we may want to store the entire config as part of the job
    def create_job(self, config) -> int:
        project_id = self.get_project_id(config['project'])

        cursor = self.DB_CONNECTION.cursor()
        sql = """
                INSERT INTO jobs(start_time, user_id, project_id)
                VALUES (CURRENT_TIMESTAMP, 1, %s)
                returning job_id
            """
        data = (project_id,)
        cursor.execute(sql, data)
        job_id = cursor.fetchone()[0]
        cursor.close()

        return job_id

    def finish_job(self, job_id: int):
        cursor = self.DB_CONNECTION.cursor()
        sql = "UPDATE jobs SET end_time = CURRENT_TIMESTAMP WHERE job_id = %s"
        data = (job_id,)
        cursor.execute(sql, data)
        cursor.close()

    def job_exists(self, job_id: int) -> bool:
        cursor = self.DB_CONNECTION.cursor()
        sql = "SELECT 1 FROM jobs WHERE job_id = %s"
        data = (job_id,)
        cursor.execute(sql, data)
        job_record = cursor.fetchone()
        cursor.close()

        return job_record is not None

    def get_current_available_clients(self, device_types: Tuple[int, str, str]) -> str:
        cursor = self.DB_CONNECTION.cursor()
        sql = """
                SELECT device_id, device_code AS hostname, device_name
                FROM devices WHERE device_name = ANY(%s) AND status = %s
            """
        data = (device_types, 'ACTIVE')
        cursor.execute(sql, data)
        db_devices = cursor.fetchall()
        cursor.close()

        return db_devices

    def register_client(self, client_id: int, dev_id: int, job_id: int) -> str:
        cursor = self.DB_CONNECTION.cursor()
        sql = """
                INSERT INTO clients (client_number, device_id, job_id)
                VALUES (%s, %s, %s) RETURNING client_id
            """
        cursor.execute(sql, (client_id, dev_id, job_id))
        client_id = cursor.fetchone()[0]
        cursor.close()

        return str(client_id)

    def get_hw_metrics(self, job_id: int, metric_writer: BinaryIO):
        cursor = self.DB_CONNECTION.cursor()
        sql = """
                COPY
                (SELECT client_number AS client_id, time, cpu_util, mem_util, gpu_util, power_consumption,
                        n_bytes_sent, n_bytes_rcvd, net_usage_out, net_usage_in
                    FROM clients
                    JOIN device_measurements USING (client_id)
                    JOIN jobs USING (job_id)
                    JOIN devices USING(device_id)
                    WHERE jobs.job_id = %s
                    ORDER BY client_number, time)
                TO STDOUT WITH (FORMAT CSV, HEADER)
               """
        data = (job_id,)
        with cursor.copy(sql, data) as copy:
            for data in copy:
                metric_writer.write(data)

        cursor.close()

    def get_round_metrics(self, job_id: int, metric_writer: BinaryIO):
        cursor = self.DB_CONNECTION.cursor()
        sql = """
                COPY
                (SELECT round_number, start_time, end_time, dist_accuracy, srv_accuracy, stage
                    FROM rounds
                    WHERE job_id = %s
                    ORDER BY round_number, start_time)
                TO STDOUT WITH (FORMAT CSV, HEADER)
               """
        data = (job_id,)
        with cursor.copy(sql, data) as copy:
            for data in copy:
                metric_writer.write(data)

        cursor.close()

    def get_client_info(self, job_id: int, metric_writer: BinaryIO):
        cursor = self.DB_CONNECTION.cursor()
        sql = """
                COPY
                (SELECT client_number AS client_id, device_code AS device_name, device_name AS device_type
                    FROM clients
                        JOIN devices USING(device_id)
                    WHERE job_id = %s
                    ORDER BY client_number)
                TO STDOUT WITH (FORMAT CSV, HEADER)
               """
        data = (job_id,)
        with cursor.copy(sql, data) as copy:
            for data in copy:
                metric_writer.write(data)

        cursor.close()

    def get_client_round_metrics(self, job_id: int, metric_writer: BinaryIO):
        cursor = self.DB_CONNECTION.cursor()
        sql = """
                COPY
                (SELECT client_number AS client_id, round_number, stage,
                        cir.start_time, cir.end_time,
                        loss, num_examples, accuracy
                    FROM clients_in_round as cir
                        JOIN rounds USING(round_id)
                        JOIN clients USING(client_id)
                    WHERE rounds.job_id = %s
                    ORDER BY client_number, round_id)
                TO STDOUT WITH (FORMAT CSV, HEADER)
               """
        data = (job_id,)
        with cursor.copy(sql, data) as copy:
            for data in copy:
                metric_writer.write(data)

        cursor.close()

    def retrieve_metrics(self, job_id: int):
        """ Retrieve client metrics for job_id """
        # Make sure job id exists
        if not self.job_exists(job_id):
            raise JobNotFoundException

        with open("hw_metrics.csv", "wb") as metric_writer:
            self.get_hw_metrics(job_id, metric_writer)

        with open("round_metrics.csv", "wb") as metric_writer:
            self.get_round_metrics(job_id, metric_writer)

        with open("client_round_metrics.csv", "wb") as metric_writer:
            self.get_client_round_metrics(job_id, metric_writer)

        with open("client_info.csv", "wb") as metric_writer:
            self.get_client_info(job_id, metric_writer)

class JobNotFoundException(ValueError):
    """Could not find the job in DB"""

class ProjectNotFoundException(ValueError):
    """Could not find the project in DB"""
