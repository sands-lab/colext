import multiprocessing
import shutil

import psycopg2
import json
import copy
import subprocess
import os
import threading
import time

from server import run_server, check_android_device_online

TRAINING_DATA = "examples/femnist_example"


class NotEnoughDevicesException(Exception):
    pass


def main():
    DB_CONNECTION = psycopg2.connect(
        host="10.0.0.100",
        database="fl_testbed_db",
        user="fl_testbed_admin",
        password="fl_testbed_admin"
    )

    CLIENTS = {}

    clients_partitions = {}

    cursor = DB_CONNECTION.cursor()

    sql = "INSERT INTO fl_testbed_logging.jobs(start_time, user_id) VALUES (CURRENT_TIMESTAMP, 1) returning job_id"
    cursor.execute(sql)

    with open("../" + TRAINING_DATA + "/config.json", 'r') as json_file:

        try:

            config_json = json.load(json_file)
            config_devices = [(client["device_name"], client["partition_id"]) for client in config_json["clients"]]

            JOB_ID = cursor.fetchone()[0]

            config_devices_names = [i[0] for i in config_devices]

            sql = "select device_id, device_code as ip, device_name from fl_testbed_logging.devices where device_name in %s and status = %s"
            data = (tuple(config_devices_names), 'ACTIVE')
            cursor.execute(sql, data)

            db_devices = cursor.fetchall()

            counter = 0
            sql = "INSERT INTO fl_testbed_logging.clients (client_number, job_id, device_id) values (%s, %s, %s)"
            data = []
            offline_devices = []
            for i in db_devices:
                cur_device_ip = i[1]
                cur_device_name = i[2]
                device_index = check_devices_config(config_devices, cur_device_name)
                if device_index > -1:
                    if check_android_device_online(cur_device_ip):
                        device_id = i[0]
                        data.append((str(counter), str(JOB_ID), str(device_id)))
                        counter += 1
                        clients_partitions[cur_device_ip] = config_devices[device_index][1]
                        # config_devices.remove(device_index)
                        del config_devices[device_index]
                    else:
                        print("Device not available: " + str(cur_device_ip))
                        offline_devices.append(cur_device_ip)
                if len(config_devices) == 0:
                    break

            if len(config_devices) > 0:
                raise NotEnoughDevicesException

            cursor.executemany(sql, data)

            sql = "SELECT a.client_id, b.device_code from fl_testbed_logging.clients a, fl_testbed_logging.devices b where a.device_id = b.device_id and job_id = %s"
            data = (str(JOB_ID),)
            cursor.execute(sql, data)
            db_clients = cursor.fetchall()

            DB_CONNECTION.commit()

            threads = []

            server_process = threading.Thread(target=run_server,
                                              args=(DB_CONNECTION, JOB_ID, CLIENTS, "10.0.0.70", 8080))
            server_process.start()

            for c in db_clients:
                CLIENTS[c[1]] = c[0]
                print("Pushing the data to client: " + c[1])
                thread = threading.Thread(target=push_data_to_device,
                                          args=(copy.deepcopy(config_json), c[0], c[1], clients_partitions[c[1]]))
                thread.start()
                threads.append(thread)
                print("Data pushed to client: " + c[1])

            for thread in threads:
                thread.join()

            threads = []

            for c in db_clients:
                print("Deploying an app to client: " + c[1])
                thread = threading.Thread(target=deploy_app_to_device,
                                          args=(c[1], ))
                thread.start()
                threads.append(thread)
                print("App deployed to client: " + c[1])

            for thread in threads:
                thread.join()

            server_process.join()

            sql = "UPDATE fl_testbed_logging.jobs SET end_time = CURRENT_TIMESTAMP where job_id = %s"
            data = (str(JOB_ID),)
            cursor.execute(sql, data)

            DB_CONNECTION.commit()

        except NotEnoughDevicesException as e:
            print(f"Not enough devices available")

    cursor.close()

    DB_CONNECTION.close()


def push_data_to_device(data, client_id, client_ip, partition_id):
    print("Pushing config file")
    os.makedirs(os.path.dirname("../temp/config_" + str(client_id) + "/fl_testbed/config.json"), exist_ok=True)
    data["client_id"] = client_id
    data["partition_id"] = partition_id + 1
    del data["clients"]
    with open("../temp/config_" + str(client_id) + "/fl_testbed/config.json", 'w') as json_file:
        json.dump(data, json_file, indent=4)

    print("Config file pushed")

    try:

        shutil.copy2('../' + TRAINING_DATA + '/app.apk', "../temp/config_" + str(client_id) + "/fl_testbed/app.apk")

        split_dataset_by_clients("../" + TRAINING_DATA + "/data", "../temp/config_" + str(client_id) + "/fl_testbed/data",
                                 "partition_" + str(partition_id) + "_test.txt")

        split_dataset_by_clients("../" + TRAINING_DATA + "/data", "../temp/config_" + str(client_id) + "/fl_testbed/data",
                                 "partition_" + str(partition_id) + "_train.txt")

        source_file = os.path.join('../' + TRAINING_DATA, 'model', 'cnn_femnist.tflite')
        destination_file = os.path.join("../temp/config_" + str(client_id) + "/fl_testbed", 'model', 'cnn_femnist.tflite')
        os.makedirs(os.path.dirname(destination_file), exist_ok=True)
        shutil.copy2(source_file, destination_file)

        subprocess.check_output(
            "adb -s " + client_ip + " push --sync ../temp/config_" + str(client_id) + "/fl_testbed/ "
                                                                                      "/storage/emulated/0/Documents/"
            , shell=True, text=True)

        subprocess.check_output("adb -s " + client_ip + " shell \'cat /storage/emulated/0/Documents/fl_testbed/app.apk "
                                                        "| pm install -t -S $(stat -c %s "
                                                        "/storage/emulated/0/Documents/fl_testbed/app.apk)\'",
                                shell=True, text=True)

    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")


def deploy_app_to_device(client_ip):
    try:
        print("Setting owner")
        subprocess.check_output(
            "adb -s " + client_ip + " shell dpm set-device-owner flwr.android_client/.logging.AdminReceiver",
            shell=True, text=True)

        print("Allowing grants")
        subprocess.check_output(
            "adb -s " + client_ip + " shell appops set --uid flwr.android_client MANAGE_EXTERNAL_STORAGE allow"
            , shell=True, text=True)

    except:
        print("Problem during privilege setting, possibly already set")

    subprocess.check_output(
        "adb -s " + client_ip + " shell input keyevent 82"
        , shell=True, text=True)

    time.sleep(1)

    print("Starting an app")
    subprocess.check_output(
        "adb -s " + client_ip + " shell am start -a android.intent.action.MAIN -n flwr.android_client/.MainActivity"
        , shell=True, text=True)


def split_dataset_by_clients(source, dest, paths_file):
    with open(os.path.join(source, paths_file), "r") as file:
        file_paths = [line.strip() for line in file]

    # Iterate through the file paths and copy the files
    for file_path in file_paths:
        source_file = os.path.join(source, file_path)
        destination_file = os.path.join(dest, file_path)
        os.makedirs(os.path.dirname(destination_file), exist_ok=True)
        shutil.copy2(source_file, destination_file)

    source_file = os.path.join(source, paths_file)
    destination_file = os.path.join(dest, paths_file)
    os.makedirs(os.path.dirname(destination_file), exist_ok=True)
    shutil.copy2(source_file, destination_file)


def check_devices_config(config_devices, device_name):
    for i, t in enumerate(config_devices):
        if t[0] == device_name:
            return i
    return -1


if __name__ == "__main__":
    main()
