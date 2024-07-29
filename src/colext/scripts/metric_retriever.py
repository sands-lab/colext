import sys
import argparse
import logging
import os
from pathlib import Path
from contextlib import contextmanager

import seaborn as sns
import matplotlib as plt
import numpy as np
import pandas as pd
from pandas import DataFrame
from colext.common.logger import log
from colext.exp_deployers.db_utils import DBUtils, JobNotFoundException

def get_args():
    parser = argparse.ArgumentParser(description='Retrieve metrics from CoLExt')
    parser.add_argument('-j', '--job_id', required=True, type=int, help="Job id to retrieve metrics")
    parser.add_argument('-o', '--output_p_dir', type=Path, default=Path("./"), help="Output parent dir for job metrics")
    # parser.add_argument('-s', '--gen_summary', help="Generate summary data")

    args = parser.parse_args()
    return args

@contextmanager
def change_cwd(new_path, mkdir=False):
    if mkdir and not os.path.isdir(new_path):
        os.makedirs(new_path)

    original_cwd = os.getcwd()
    try:
        os.chdir(new_path)
        yield
    finally:
        os.chdir(original_cwd)

def retrieve_metrics():
    log.setLevel(logging.INFO)
    args = get_args()
    job_id = args.job_id
    output_dir = f"{args.output_p_dir}/colext_metrics/{job_id}"

    with change_cwd(f"{output_dir}/raw", mkdir=True):
        print("Retrieving metrics")
        download_metric_files(job_id)

        print("Generating client summary timings")
        client_rounds_summary = gen_cr_metric_summary()

    with change_cwd(f"{output_dir}/plots", mkdir=True):
        print("Creating plots")
        plot_summary_data(client_rounds_summary)

def download_metric_files(job_id):
    db = DBUtils()
    try:
        db.retrieve_metrics(job_id)
    except JobNotFoundException:
        print(f"Could not find job with id {job_id}")
        sys.exit(1)

def gen_cr_metric_summary():
    # Assumes local dir has data
    jd = read_metric_files()

    jd["hw_metrics"] = clean_up_hw(jd)
    client_rounds_summary = clean_up_cr(jd)

    client_rounds_summary.to_csv('client_rounds_summary.csv', index=False)
    return client_rounds_summary

def read_metric_files():
    # FIX: Why set_index?
    client_info: DataFrame = pd.read_csv("client_info.csv").set_index("client_id")
    round_metrics: DataFrame = pd.read_csv("round_metrics.csv", parse_dates=["start_time", "end_time"])
    cr_timings: DataFrame = pd.read_csv("client_round_metrics.csv", parse_dates=["start_time", "end_time"])
    # FIX: I want to merge these two lines
    hw_metrics: DataFrame = pd.read_csv("hw_metrics.csv")
    hw_metrics["time"] = pd.to_datetime(hw_metrics["time"], format='ISO8601')
    # FIX: Can we set the index to time?

    job_data = {
        "client_info": client_info,
        "cr_timings": cr_timings,
        "hw_metrics": hw_metrics,
        "round_metrics": round_metrics
    }

    return job_data

def clean_up_hw(jd):
    round_metrics, hw_metrics = jd["round_metrics"], jd["hw_metrics"]
    # Clip HW measurements to start at first round and finish at last round
    start_time = round_metrics["start_time"].min()
    end_time = round_metrics["end_time"].max()
    # FIX: Why copy?
    hw_metrics = hw_metrics[(hw_metrics["time"] > start_time) & (hw_metrics["time"] < end_time)].copy()

    # Compute energy from power
    def comp_comulative_energy(group):
        group['delta_t_sec'] = group['time'].diff().dt.total_seconds().fillna(0)
        group['energy'] = (group['power_consumption'] * group['delta_t_sec']).cumsum()
        return group
    hw_metrics = hw_metrics.groupby('client_id').apply(comp_comulative_energy).reset_index(drop=True)

    # Adjust HW Units:
    hw_metrics["mem_util"] = hw_metrics["mem_util"] / 1024 / 1024 # MiB
    hw_metrics["power_consumption"] = hw_metrics["power_consumption"] / 1000 # W
    hw_metrics["energy"] = hw_metrics["energy"] / 1000 / 1000 # From mJ -> KJ
    hw_metrics["n_bytes_sent"] = hw_metrics["n_bytes_sent"] / 1024 / 1024 # MiB
    hw_metrics["n_bytes_rcvd"] = hw_metrics["n_bytes_rcvd"] / 1024 / 1024 # MiB
    hw_metrics["net_usage_out"] = hw_metrics["net_usage_out"] / 1024 / 1024  # MiB/s
    hw_metrics["net_usage_in"] =  hw_metrics["net_usage_in"]  / 1024 / 1024 # MiB/s

    # Rename columns
    hw_metrics.rename(columns={
        "cpu_util": "CPU Util (%)",
        "gpu_util": "GPU Util (%)",
        "mem_util": "Mem Util (MiB)",
        "power_consumption": "Power (W)",
        "energy": "Energy (KJ)",
        "n_bytes_sent": "Sent (MiB)",
        "n_bytes_rcvd": "Rcvd (MiB)",
        "net_usage_out": "Upload (MiB/s)",
        "net_usage_in":  "Download (MiB/s)",
        }, inplace=True)

    return hw_metrics

def clean_up_cr(jd):
    round_metrics, hw_metrics, cr_timings, client_info = jd["round_metrics"], jd["hw_metrics"], jd["cr_timings"], jd["client_info"]

    # Add round time to cr_timings
    round_metrics['Round time (s)'] = (round_metrics['end_time'] - round_metrics['start_time']).dt.total_seconds()
    cr_timings = cr_timings.merge(round_metrics[['round_number', 'Round time (s)']], on='round_number')
    cr_timings['Training time (s)'] = (cr_timings['end_time'] - cr_timings['start_time']).dt.total_seconds()

    def collect_energy_metrics_client_rounds(cr_metrics, hw_metrics, round_metrics):
        def get_energy(cr_group):
            cid, r_num, stage = cr_group.name

            hw_group = hw_metrics[hw_metrics["client_id"] == cid]
            # happens when evaluate is too fast
            if hw_group.empty:
                cr_group["Energy training (J)"] = np.nan
                cr_group["Energy in round (J)"] = np.nan
            else:
                hw_group.set_index("time", inplace=True)

                start_i = hw_group.index.get_indexer(cr_group["start_time"], method="nearest")
                end_i = hw_group.index.get_indexer(cr_group["end_time"], method="nearest")
                cr_group["Energy training (J)"] = (hw_group.iloc[end_i]["Energy (KJ)"][0] - hw_group.iloc[start_i]["Energy (KJ)"][0]) * 1000 # (KJ -> J)

                round_metric_f = round_metrics.query(f"round_number == {r_num} and stage == '{stage}'")
                start_i = hw_group.index.get_indexer(round_metric_f["start_time"], method="nearest")
                end_i = hw_group.index.get_indexer(round_metric_f["end_time"], method="nearest")
                cr_group["Energy in round (J)"] = (hw_group.iloc[end_i]["Energy (KJ)"][0] - hw_group.iloc[start_i]["Energy (KJ)"][0]) * 1000 # (KJ -> J)

            return cr_group
        group_cols = ["client_id", "round_number", "stage"]
        return cr_metrics.groupby(group_cols).apply(get_energy).reset_index(drop=True)

    cr_timings = collect_energy_metrics_client_rounds(cr_timings, hw_metrics, round_metrics)
    cr_timings['EDP (J*s)'] = cr_timings['Energy training (J)'] * cr_timings['Training time (s)']

    cr_timings['Training time ps (ms)'] = cr_timings.apply(lambda row: row["Training time (s)"] / row["num_examples"] * 1000, axis=1)
    cr_timings['Energy ps (mJ)'] = cr_timings.apply(lambda row: row["Energy training (J)"] / row["num_examples"] * 1000 , axis=1)
    cr_timings['EDP ps (mJ*ms)'] = cr_timings['Training time ps (ms)'] * cr_timings['Energy ps (mJ)']

    # Add client device name and type
    cr_timings = cr_timings.join(client_info, on="client_id")

    return cr_timings

def plot_cir_metrics(df, interest_cols, save_file, row="device_type"):
    """Convert to long format and print facetgrid with metrics"""
    id_vars=[row, "stage"]
    cols = [row, "stage"] + interest_cols

    df = df[cols]
    df_long = pd.melt(df, id_vars=id_vars, var_name='metric')

    g = sns.catplot(x="value", y=row, hue=row, data=df_long,
                    col="metric", row="stage",
                    row_order=["FIT", "EVAL"],
                    kind="bar", sharex=False, height=3)
    g.set_axis_labels("", "")
    g.set_titles(col_template="{col_name}", row_template="{row_name}")
    g.figure.savefig(save_file)

def plot_summary_data(summary_data):
    interest_cols = ["Training time (s)", "Energy training (J)", "Energy in round (J)", 'EDP (N)']
    # 1 Plot
    row = "device_type"
    mean_edp_by_dev_type = summary_data.groupby(row)['EDP (J*s)'].mean()
    min_mean_edp = mean_edp_by_dev_type.min()
    summary_data['EDP (N)'] = summary_data.groupby('stage')['EDP (J*s)'].transform(lambda x: x / min_mean_edp)
    plot_cir_metrics(summary_data, interest_cols, row=row, save_file="per_dev_type.pdf")

    # 2 Plot
    row = "device_name"
    mean_edp_by_dev_name = summary_data.groupby(row)['EDP (J*s)'].mean()
    min_mean_edp = mean_edp_by_dev_name.min()
    summary_data['EDP (N)'] = summary_data.groupby('stage')['EDP (J*s)'].transform(lambda x: x / min_mean_edp)
    plot_cir_metrics(summary_data, interest_cols, row=row, save_file="per_dev.pdf")

    interest_cols = ["Training time ps (ms)", "Energy ps (mJ)", "EDP ps (N)"]
    # 3 Plot
    row = "device_type"
    mean_edp = summary_data.groupby(row)['EDP ps (mJ*ms)'].mean()
    min_mean_edp = mean_edp.min()
    summary_data['EDP ps (N)'] = summary_data.groupby('client_id')['EDP ps (mJ*ms)'].transform(lambda x: x / min_mean_edp)
    plot_cir_metrics(summary_data, interest_cols, row=row, save_file="ps_per_dev_type.pdf")

    # 4 Plot
    row = "device_name"
    mean_edp = summary_data.groupby(row)['EDP ps (mJ*ms)'].mean()
    min_mean_edp = mean_edp.min()
    summary_data['EDP ps (N)'] = summary_data.groupby('client_id')['EDP ps (mJ*ms)'].transform(lambda x: x / min_mean_edp)
    plot_cir_metrics(summary_data, interest_cols, row=row, save_file="ps_per_dev.pdf")
