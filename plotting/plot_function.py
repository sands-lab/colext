import os
from pathlib import Path
import subprocess
from subprocess import CompletedProcess
import seaborn as sns
import pandas as pd
from pandas import DataFrame
import numpy as np
import matplotlib.pyplot as plt

def collect_job_metrics(job_details):
    job_id = job_details["id"]
    command = ["colext_get_metrics", "-j", str(job_id)]
    job_metric_dir = Path(f"metrics/{job_details['exp_name']}")

    if not os.path.isdir(job_metric_dir):
        os.makedirs(job_metric_dir, exist_ok=True)
        result: CompletedProcess = subprocess.run(command, capture_output=True, cwd=job_metric_dir, check=True)
        if result.returncode != 0:
            print(f"ERROR: Could not collect job metrics for job_id = {job_id}")
            os.rmdir(job_metric_dir)

    job_data = read_job_metrics(job_details, job_metric_dir)

    return job_data

def comp_comulative_energy_hw_metrics(group):
    group['delta_t_sec'] = group['time'].diff().dt.total_seconds().fillna(0)
    group['energy'] = (group['power_consumption'] * group['delta_t_sec']).cumsum()
    return group

def reset_network_counts_to_min(group):
    min_index = group['time'].idxmin()

    min_n_bytes_sent = group.loc[min_index, 'n_bytes_sent']
    min_n_bytes_rcvd = group.loc[min_index, 'n_bytes_rcvd']

    group["n_bytes_sent"] -= min_n_bytes_sent
    group["n_bytes_rcvd"] -= min_n_bytes_rcvd
    return group

def collect_energy_metrics_client_rounds(cr_metrics, hw_metrics, round_metrics):
    group_cols = ["client_id", "round_number", "stage"]
    def get_energy(cr_group):
        cid, r_num, stage = cr_group.name

        hw_group = hw_metrics[hw_metrics["client_id"] == cid]
        # if hw_group empty, we don't have a measurement for that stage
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
    return cr_metrics.groupby(group_cols).apply(get_energy).reset_index(drop=True)

def add_round_and_stage_to_hw_metrics(hw_metrics, round_metrics):
    time_bins = round_metrics["start_time"].tolist() + [round_metrics["end_time"].max()]
    labels = round_metrics["round_number"].tolist()
    hw_metrics['round_number'] = pd.cut(hw_metrics['time'], bins=time_bins, labels=labels, right=False, ordered=False)
    labels = round_metrics["stage"].tolist()
    hw_metrics['stage'] = pd.cut(hw_metrics['time'], bins=time_bins, labels=labels, right=False, ordered=False)

def clip_data(round_metrics, cr_timings, hw_metrics, job_details):
    # Cleaning NA values (introduced when clients crash)
    na_ids = cr_timings.isna().any(axis=1)
    if na_ids.empty:
        print(f"Removing the following entries with Nan values from cr_timings {cr_timings[na_ids]}")
        cr_timings.dropna(inplace=True)

    # Clip to max_rounds
    job_max_round = cr_timings["round_number"].max()
    max_round =  job_details.get("max_round", job_max_round)
    if job_max_round != max_round:
        print(f"Clipping rounds to {max_round}")

    cr_timings = cr_timings[cr_timings["round_number"] <= max_round]

    # Only consider FIT data for now
    # pb for EVAL part will be wrong so we only do FIT
    cr_timings = cr_timings[cr_timings["stage"] == "FIT"]

    round_metrics = round_metrics[round_metrics["stage"] == "FIT"]

    # Clip HW measurements to start at first round and finish at last round
    start_time = round_metrics["start_time"].min()
    end_time = round_metrics["end_time"].max()
    hw_metrics = hw_metrics[(hw_metrics["time"] > start_time) & (hw_metrics["time"] < end_time)].copy()
    # hw_metrics = hw_metrics.groupby("client_id").apply(reset_network_counts_to_min).reset_index(drop=True)

    return cr_timings, hw_metrics, round_metrics

def adjust_hw_units(hw_metrics):
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

def compute_cr_additional_cols(cr_timings, hw_metrics, round_metrics, job_details):
    cr_timings['Training time (s)'] = (cr_timings['end_time'] - cr_timings['start_time']).dt.total_seconds()
    # Get energy per round per client + energy only for client training time
    cr_timings = collect_energy_metrics_client_rounds(cr_timings, hw_metrics, round_metrics)
    cr_timings['EDP (J*s)'] = cr_timings['Energy training (J)'] * cr_timings['Training time (s)']

    # Add round time to cr_timings
    cr_timings = cr_timings.merge(round_metrics[['round_number', 'Round time (s)']], on='round_number')

    data_batches = job_details.get("data_batches")
    epochs = job_details.get("epochs", 1)
    if data_batches:
        cr_timings['Training time pb (s)'] = cr_timings.apply(lambda row: row["Training time (s)"] / data_batches[row["client_id"]] / epochs, axis=1)
        cr_timings['Energy pb (J)'] = cr_timings.apply(lambda row: row["Energy training (J)"] / data_batches[row["client_id"]] / epochs, axis=1)
        cr_timings['EDP pb (J*s)'] = cr_timings['Training time pb (s)'] * cr_timings['Energy pb (J)']
    else:
        print("Data samples was not specified, will not compute per sample columns")

    return cr_timings

def read_job_metrics(job_details, job_metric_dir):
    job_id = job_details["id"]
    path_prefix = f"{job_metric_dir}/colext_{job_id}"

    client_info: DataFrame = pd.read_csv(f"{path_prefix}_client_info.csv").set_index("client_id")
    round_metrics: DataFrame = pd.read_csv(f"{path_prefix}_round_metrics.csv", parse_dates=["start_time", "end_time"])
    cr_timings: DataFrame = pd.read_csv(f"{path_prefix}_client_round_timings.csv", parse_dates=["start_time", "end_time"])
    hw_metrics: DataFrame = pd.read_csv(f"{path_prefix}_hw_metrics.csv")
    hw_metrics["time"] = pd.to_datetime(hw_metrics["time"], format='ISO8601')

    cr_timings, hw_metrics, round_metrics = clip_data(round_metrics, cr_timings, hw_metrics, job_details)

    # Compute energy from power
    hw_metrics = hw_metrics.groupby('client_id').apply(comp_comulative_energy_hw_metrics).reset_index(drop=True)
    # add_round_and_stage_to_hw_metrics(hw_metrics, round_metrics)
    adjust_hw_units(hw_metrics)

    round_metrics['Round time (s)'] = (round_metrics['end_time'] - round_metrics['start_time']).dt.total_seconds()

    cr_timings = compute_cr_additional_cols(cr_timings, hw_metrics, round_metrics, job_details)

    # Add client device name and type
    cr_timings = cr_timings.join(client_info, on="client_id")
    hw_metrics = hw_metrics.join(client_info, on="client_id")

    # Simplify names if we're only using Jetsons
    if client_info["device_type"].str.startswith("Jetson").all():
        mapping = {
        "JetsonAGXOrin": "AGXOrin",
        "JetsonOrinNano": "OrinNano",
        "JetsonXavierNX": "XavierNX",
        "JetsonNano": "Nano",
        }
        cr_timings['device_type'] = cr_timings['device_type'].replace(mapping)

    job_data = {}
    job_data["client_info"] = client_info
    job_data["cr_timings"] = cr_timings
    job_data["hw_metrics"] = hw_metrics
    job_data["round_metrics"] = round_metrics
    return job_data

def plot_hw_metrics(df, id_vars="device_type", save_name=None):
    """Convert to long format and print facetgrid with metrics"""
    df_long = pd.melt(df, id_vars=id_vars, var_name='metric')

    order=["JetsonAGXOrin", "JetsonOrinNano", "JetsonXavierNX", "JetsonNano", "LattePandaDelta3", "OrangePi5B"]
    g = sns.catplot(x="value", y="device_type", col="metric", hue="device_type", data=df_long,
                kind="bar", order=order, sharex=False, height=3)
    g.set_axis_labels("", "")
    g.set_titles("{col_name}")
    plt.tight_layout()
    if save_name:
        g.figure.savefig(f"plots/{save_name}")
    g.figure.show()

def plot_cir_metrics(df, job_details, row="device_type", order=None, save_file=None, cols_per_batch=False, show=True):
    """Convert to long format and print facetgrid with metrics"""
    id_vars=[row, "stage"]
    cols = [row, "stage"]

    if cols_per_batch:
        cols += ["Training time pb (s)", "Energy pb (J)", 'EDP pb (N)']
    else:
        cols += ["Training time (s)", "Energy training (J)", "Energy in round (J)", 'EDP (N)']

    df = df[cols]
    df_long = pd.melt(df, id_vars=id_vars, var_name='metric')

    if order is None:
        order_field = "dev_order" if row == "device_name" else "dev_type_order"
        order = job_details.get(order_field)

    g = sns.catplot(x="value", y=row, col="metric", hue=row, data=df_long,
                    kind="bar", order=order, sharex=False, height=3)
    g.set_axis_labels("", "")
    # g.set_titles(col_template="{col_name}", row_template="{row_name}")
    g.set_titles(col_template="{col_name}")
    plt.tight_layout()
    if save_file:
        g.figure.savefig(save_file)
    if show:
        g.figure.show()

def full_algo_plot(cr_timings, job_details, show=True):
    exp_name = job_details['exp_name']

    plots_dir = f"plots/{exp_name}"
    os.makedirs(plots_dir, exist_ok=True)

    # 1 Plot
    # row = "device_type"
    # mean_edp_by_dev_type = cr_timings.groupby(row)['EDP (J*s)'].mean()
    # min_mean_edp = mean_edp_by_dev_type.min()
    # cr_timings['EDP (N)'] = cr_timings.groupby('stage')['EDP (J*s)'].transform(lambda x: x / min_mean_edp)
    # plot_cir_metrics(cr_timings, job_details, row=row)

    # 2 Plot
    row = "device_name"
    mean_edp_by_dev_name = cr_timings.groupby(row)['EDP (J*s)'].mean()
    min_mean_edp = mean_edp_by_dev_name.min()
    cr_timings['EDP (N)'] = cr_timings.groupby('stage')['EDP (J*s)'].transform(lambda x: x / min_mean_edp)
    plot_cir_metrics(cr_timings, job_details, row=row, save_file=f"{plots_dir}/per_dev.pdf", show=show)

    # 3 Plot
    row = "device_type"
    mean_edp = cr_timings.groupby(row)['EDP pb (J*s)'].mean()
    min_mean_edp = mean_edp.min()
    cr_timings['EDP pb (N)'] = cr_timings.groupby('client_id')['EDP pb (J*s)'].transform(lambda x: x / min_mean_edp)
    plot_cir_metrics(cr_timings, job_details, row=row, cols_per_batch=True, save_file=f"{plots_dir}/pb_per_dev_type.pdf", show=show)

    # 4 Plot
    row = "device_name"
    mean_edp = cr_timings.groupby(row)['EDP pb (J*s)'].mean()
    min_mean_edp = mean_edp.min()
    cr_timings['EDP pb (N)'] = cr_timings.groupby('client_id')['EDP pb (J*s)'].transform(lambda x: x / min_mean_edp)
    plot_cir_metrics(cr_timings, job_details, row=row, cols_per_batch=True, save_file=f"{plots_dir}/pb_per_dev.pdf", show=show)

def cmp_algorithms_by_cir(cir_list, row, perb=False, N=True, save_file=None):
    cols = []
    if perb:
        cols = ["Training time pb (s)", "Energy pb (J)", "EDP pb (J*s)"]
    else:
        cols = ["Training time (s)", "Energy training (J)", "EDP (J*s)"]

    df = pd.concat(cir_list, axis=0, ignore_index=True)

    if N:
        n_columns = len(cols)
        for i in range(n_columns):
            col_name = cols[i]
            min_mean = df.groupby([row, 'Algorithm'])[col_name].mean().min()
            N_col_name = re.sub(r'\(.*\)', '(N)', col_name)
            df[N_col_name] = df.groupby('client_id')[col_name].transform(lambda x: x / min_mean)
            cols[i] = N_col_name

    cols += ["Algorithm", row]
    df = df[cols]
    df_long = pd.melt(df, id_vars=[row, "Algorithm"], var_name='metric')
    # g = sns.catplot(x="value", y=row, col="metric", hue='Algorithm', data=df_long,
    g = sns.catplot(x="value", y='Algorithm', col="metric", hue=row, data=df_long,
                    kind="bar", sharex=False, height=2.15, aspect=0.82, col_wrap=2)
                    # kind="bar", sharex=False, height=3, aspect=0.905, col_wrap=2)
    g.set_axis_labels("", "")
    g.set_titles(col_template="{col_name}")
    # for i, ax in enumerate(g.axes[0]):
    #     if i == 2:
    #         continue
    #     ax.xaxis.set_major_locator(ticker.MultipleLocator(1))

    if row == "device_type":
        title = "Device Type"
    # sns.move_legend(g, loc="center left", handlelength=0.7, bbox_to_anchor=(1.0, 0.5), frameon=True)
    # sns.move_legend(g, loc="lower left", handlelength=0.7, frameon=True, mode = "expand", ncol=len(df.device_type))
    # sns.move_legend(g, loc="upper center", title=title, handlelength=0.7, frameon=True, ncol=len(df.device_type), bbox_to_anchor=(0.5,0.05))
    sns.move_legend(g, loc="lower right", title=title, frameon=True, bbox_to_anchor=(0.95,0.09))
    plt.tight_layout()
    if save_file:
        g.figure.savefig(save_file, bbox_inches='tight')
    plt.show()

def comp_algorithms_by_round_metrics(df_list, save_file=None):
    df = pd.concat(df_list, axis=0, ignore_index=True)
    df["Energy in round (J)"] = df.groupby(['Algorithm', 'round_number'])["Energy in round (J)"].transform('sum')
    cols = ["Round time (s)", "Energy in round (J)"]

    n_columns = len(cols)
    for i in range(n_columns):
        col_name = cols[i]
        min_mean = df.groupby(['Algorithm'])[col_name].mean().min()
        N_col_name = re.sub(r'\(.*\)', '(N)', col_name)
        df[N_col_name] = df.groupby('client_id')[col_name].transform(lambda x: x / min_mean)
        cols[i] = N_col_name


    cols += ["Algorithm"]
    df = df[cols]
    print(df.groupby('Algorithm').describe())

    df_long = pd.melt(df, id_vars=["Algorithm"], var_name='metric')
    g = sns.catplot(x="value", y='Algorithm', col="metric", hue='Algorithm',
                kind='bar', order=["Moon (L)", "Moon (L+O)", "Fedprox (L)"], data=df_long,
                height=2, aspect=1.5)
    g.set_axis_labels("", "")
    g.set_titles(col_template="{col_name}")

    if save_file:
        g.figure.savefig(save_file, bbox_inches='tight')
    plt.show()


