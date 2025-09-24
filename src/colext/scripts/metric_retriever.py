import sys
import argparse
import logging
import os
from pathlib import Path
from contextlib import contextmanager

import seaborn as sns
import numpy as np
import pandas as pd
from pandas import DataFrame
from colext.common.logger import log
from colext.exp_deployers.db_utils import DBUtils, JobNotFoundException

def get_args():
    parser = argparse.ArgumentParser(description='Retrieve metrics from CoLExt')
    parser.add_argument('-j', '--job_id', required=True, type=int, help="Job id to retrieve metrics")
    parser.add_argument('-o', '--output_p_dir', type=Path, default=Path("./"), help="Output parent dir for job metrics")
    parser.add_argument('-f', '--force_collect', action='store_true', help="Force collect metrics when output dir for job exists")
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

    if os.path.isdir(output_dir) and not args.force_collect:
        print(f"Skippiging metric retrieval for job {job_id} because the output dir '{output_dir}' already exists.")
        print("Use the -f flag to force retrieval of metrics.")
        return

    with change_cwd(f"{output_dir}/raw", mkdir=True):
        print(f"Retrieving metrics for job {job_id}")
        download_metric_files(job_id)
        jd = read_metric_files()

        print("Generating cleaned HW metrics")
        jd["hw_metrics_cleaned"] = gen_clean_hw_metrics(jd)

        print("Generating client summary timings")
        client_rounds_summary = gen_cr_metric_summary(jd)

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

def read_metric_files():
    # FIX: Why set_index?
    client_info: DataFrame = pd.read_csv("client_info.csv").set_index("client_id")
    round_metrics: DataFrame = pd.read_csv("round_metrics.csv")
    cr_timings: DataFrame = pd.read_csv("client_round_metrics.csv")
    hw_metrics: DataFrame = pd.read_csv("hw_metrics.csv")
    # FIX: Can we set the index to time?

    # Parse dates
    round_metrics["start_time"] = pd.to_datetime(round_metrics["start_time"], format='ISO8601')
    round_metrics["end_time"]   = pd.to_datetime(round_metrics["end_time"],   format='ISO8601')
    cr_timings["start_time"]    = pd.to_datetime(cr_timings["start_time"],    format='ISO8601')
    cr_timings["end_time"]      = pd.to_datetime(cr_timings["end_time"],      format='ISO8601')
    hw_metrics["time"]          = pd.to_datetime(hw_metrics["time"],          format='ISO8601')

    job_data = {
        "client_info": client_info,
        "cr_timings": cr_timings,
        "hw_metrics": hw_metrics,
        "round_metrics": round_metrics
    }

    return job_data

def gen_clean_hw_metrics(jd):
    round_metrics, hw_metrics, cr_timings = jd["round_metrics"], jd["hw_metrics"], jd["cr_timings"]
    # Clip HW measurements to start at first round and finish at last round
    start_time = round_metrics.query("round_number == 1 and stage == 'FIT'")["start_time"].min()
    end_time = round_metrics["end_time"].max()
    # Copy to create a new df - otherwise it would be a view
    hw_metrics = hw_metrics[(hw_metrics["time"] > start_time) & (hw_metrics["time"] < end_time)].copy()

    # Compute energy from power
    def comp_comulative_energy(group):
        group['delta_t_sec'] = group['time'].diff().dt.total_seconds().fillna(0)
        group['energy'] = (group['power_consumption'] * group['delta_t_sec']).cumsum()
        return group

    hw_metrics = hw_metrics.groupby('client_id') \
                           .apply(comp_comulative_energy, include_groups=True) \
                           .reset_index(drop=True)

    def attach_round_stage_state(client_i_hw):
        client_id = client_i_hw.name
        time_values = client_i_hw["time"].to_numpy()
        for _, row in round_metrics.iterrows():
            start_i = time_values.searchsorted(row["start_time"], side="left")
            end_i = time_values.searchsorted(row["end_time"], side="right") - 1

            client_i_hw.loc[client_i_hw.index[start_i:end_i + 1], "round_number"] = row["round_number"]
            client_i_hw.loc[client_i_hw.index[start_i:end_i + 1], "stage"] = row["stage"]

        client_i_cr = cr_timings[cr_timings["client_id"] == client_id]
        for _, row in client_i_cr.iterrows():
            start_i = time_values.searchsorted(row["start_time"], side="left")
            end_i = time_values.searchsorted(row["end_time"], side="right") - 1

            client_i_hw.loc[client_i_hw.index[start_i:end_i + 1], "state"] = "run"

        return client_i_hw

    # prime state to idle - set running state during training portion
    hw_metrics["state"] = "idle"
    hw_metrics = hw_metrics.groupby("client_id").apply(attach_round_stage_state, include_groups=True)

    # Adjust HW Units:
    hw_metrics["mem_util"] = hw_metrics["mem_util"] / 1024 / 1024 # MiB
    hw_metrics["power_consumption"] = hw_metrics["power_consumption"] / 1000 # W
    hw_metrics["energy"] = hw_metrics["energy"] / 1000 / 1000 # From mJ -> KJ
    hw_metrics["n_bytes_sent"] = hw_metrics["n_bytes_sent"] / 1024 / 1024 # MiB
    hw_metrics["n_bytes_rcvd"] = hw_metrics["n_bytes_rcvd"] / 1024 / 1024 # MiB
    hw_metrics["net_usage_out"] = hw_metrics["net_usage_out"] / 1024 / 1024  # MiB/s
    hw_metrics["net_usage_in"] =  hw_metrics["net_usage_in"]  / 1024 / 1024 # MiB/s

    hw_metrics["round_number"] = hw_metrics["round_number"].astype("Int64")

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

    hw_metrics.to_csv('hw_metrics_cleaned.csv', index=False)
    return hw_metrics

def gen_cr_metric_summary(jd):
    round_metrics, hw_metrics, cr_timings, client_info = jd["round_metrics"], jd["hw_metrics_cleaned"], jd["cr_timings"], jd["client_info"]

    # crs = client round summary
    crs = cr_timings
    crs = crs.merge(round_metrics[['round_number', 'stage', 'Round time (s)']], on=['round_number', 'stage'])
    crs['Training time (s)'] = (crs['end_time'] - crs['start_time']).dt.total_seconds()

    def get_scoped_metrics(cr_group):
        cid, r_num, stage = cr_group.name

        hw_group = hw_metrics[hw_metrics["client_id"] == cid]
        # happens when evaluate is too fast
        if hw_group.empty:
            cr_group.loc[:,
                            ["Energy training (J)",
                            "Energy in round (J)",
                            "Data rcvd in round (MiB)",
                            "Data sent in round (MiB)"]] = np.nan
        else:
            hw_group.set_index("time", inplace=True)

            def calc_diff(start_i, end_i, col):
                return hw_group.iloc[end_i][col] - hw_group.iloc[start_i][col]

            # Scoped to training
            start_i = hw_group.index.get_indexer(cr_group["start_time"], method="nearest")[0]
            end_i = hw_group.index.get_indexer(cr_group["end_time"], method="nearest")[0]
            cr_group["Energy training (J)"] = calc_diff(start_i, end_i, "Energy (KJ)") * 1000 # (KJ -> J)

            df = hw_group.iloc[start_i:end_i].groupby(["round_number", "stage"])[
                ["CPU Util (%)", "GPU Util (%)", "Mem Util (MiB)", "Upload (MiB/s)", "Download (MiB/s)"]
            ].agg(["mean", "max"])
            # Flatten MultiIndex columns
            df.columns = [f"Avg {col[0]}" if col[1] == "mean" else f"Max {col[0]}" for col in df.columns]
            cr_group = cr_group.merge(df, on=["round_number", "stage"])

            # Scoped to round
            round_metric_f = round_metrics.query(f"round_number == {r_num} and stage == '{stage}'")
            start_i = hw_group.index.get_indexer(round_metric_f["start_time"], method="nearest")[0]
            end_i = hw_group.index.get_indexer(round_metric_f["end_time"], method="nearest")[0]
            cr_group["Energy in round (J)"] = calc_diff(start_i, end_i, "Energy (KJ)") * 1000 # (KJ -> J)
            cr_group["Data sent in round (MiB)"] = calc_diff(start_i, end_i, "Sent (MiB)")
            cr_group["Data rcvd in round (MiB)"] = calc_diff(start_i, end_i, "Rcvd (MiB)")

        return cr_group
    crs = crs.groupby(["client_id", "round_number", "stage"]) \
        .apply(get_scoped_metrics, include_groups=True).reset_index(drop=True)

    crs['EDP (J*s)'] = crs['Energy training (J)'] * crs['Training time (s)']

    crs['Training time ps (ms)'] = crs.apply(lambda row: row["Training time (s)"] / row["num_examples"] * 1000, axis=1)
    crs['Energy ps (mJ)'] = crs.apply(lambda row: row["Energy training (J)"] / row["num_examples"] * 1000 , axis=1)
    crs['EDP ps (mJ*ms)'] = crs['Training time ps (ms)'] * crs['Energy ps (mJ)']

    # Add client device name and type
    crs = crs.join(client_info, on="client_id")

    crs.sort_values(by=["client_id", "round_number", "start_time"], inplace=True)
    crs.to_csv('client_rounds_summary.csv', index=False)

    return crs

def plot_cir_metrics(df, interest_cols, save_file, row="dev_type"):
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
    row = "dev_type"
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
    row = "dev_type"
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

if __name__ == "__main__":
    retrieve_metrics()

