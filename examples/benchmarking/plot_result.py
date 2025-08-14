import os
import argparse
import subprocess
from matplotlib import pyplot as plt, rcParams
import seaborn as sns
import pandas as pd
import numpy as np

rcParams["savefig.format"] = 'png'
OUTPUT_FORMAT_CONFIG = {"bbox_inches": 'tight', "dpi": 300}

def make_plots(job_ids_file, benchmark_output, args):
    plots_dir = os.path.join(benchmark_output, "plots")
    if not os.path.isdir(plots_dir):
        os.makedirs(plots_dir)

    job_summaries_df, round_metrics_df, hw_metrics_df, server_metrics_df = prepare_data(job_ids_file, benchmark_output, args.force_collect)

    # Filter data
    job_summaries_df = job_summaries_df[(job_summaries_df["round_number"] > 1) & (job_summaries_df["stage"] == "FIT")]

    print("Creating plots")
    # Plots total execution time and energy consumption
    plot_totals(round_metrics_df, job_summaries_df, plots_dir)

    # Plots accuracies and how they change across rounds and overtime
    plot_accuracies(round_metrics_df, plots_dir)


    # Plots per sample data
    dev_order = ["JetsonAGXOrin", "JetsonOrinNano", "JetsonXavierNX", "JetsonNano", "JetsonXavierNX", "OrangePi5B"]
    header_cols = ["Training time ps (ms)", "Energy ps (mJ)"]
    cat_plot(job_summaries_df, plots_dir, "per_dev_ps", header_cols, x_col="dev_type", hue_col="job_id",
             extra_plot_args={
                 "order": dev_order
                 }
            )

    # Minimal plot with key metrics
    header_cols = [
        "Training time (s)", "Idle time (s)", "Energy training (J)", "Server time (s)",
    ]
    cat_plot(job_summaries_df, plots_dir, "per_job_round_minimal", header_cols, x_col="job_id", hue_col="dev_type")

    # Minimal plot with key metrics per dev type
    cat_plot(job_summaries_df, plots_dir, "per_job_per_dev_type_round_minimal", header_cols, x_col="dev_type", hue_col="job_id")

    header_cols = [
        "Training time (s)", "Idle time (s)", "num_examples", "Energy training (J)", "Server time (s)",
    ]
    # Minimal plot with key metrics per dev
    cat_plot(job_summaries_df, plots_dir, "per_job_per_dev_round_minimal", header_cols, x_col="device_name", hue_col="job_id")

    # Plot most metrics with job on the x axis and dev as hue
    header_cols = [
        "Round time (s)", "Training time (s)", "Idle time (s)", "Server time (s)",
        "Energy training (J)", "Energy in round (J)",
        "Avg CPU Util (%)", "Max CPU Util (%)",
        "Avg GPU Util (%)", "Max GPU Util (%)",
        "Avg Mem Util (MiB)", "Max Mem Util (MiB)",
        "Data rcvd in round (MiB)", "Data sent in round (MiB)",
        "Avg Download (MiB/s)", "Max Download (MiB/s)",
        "Avg Upload (MiB/s)", "Max Upload (MiB/s)",
    ]
    cat_plot(job_summaries_df, plots_dir, "per_job_round_full", header_cols, x_col="job_id", hue_col="dev_type",
                # extra_plot_args = {
                #     "errorbar": None,
                #     "estimator": np.max
                #     }
                )

    # Flip previous plot - Plot most metrics with dev on the x axis and job as hue
    cat_plot(job_summaries_df, plots_dir, "per_dev_round", header_cols, x_col="dev_type", hue_col="job_id")


def prepare_data(job_ids_file, benchmark_output, force_collect=False):
    print(f"Reading job ids from '{job_ids_file}'")
    with open(job_ids_file, "r", encoding="utf-8") as f:
        job_id_map = dict(line.strip().split('=', 1) for line in f.readlines())
    job_ids = job_id_map.keys()

    print("Preparing data")
    collect_job_metrics(job_ids, benchmark_output, force_collect)
    job_summaries_df = read_colext_metric_file_as_df("client_rounds_summary.csv", job_id_map, benchmark_output)
    round_metrics_df = read_colext_metric_file_as_df("round_metrics.csv", job_id_map, benchmark_output)
    hw_metrics_df = read_colext_metric_file_as_df("hw_metrics_cleaned.csv", job_id_map, benchmark_output, date_columns=["time"])
    server_metrics_df = read_colext_metric_file_as_df("server_round_metrics.csv", job_id_map, benchmark_output,
                                                      date_columns=["eval_time_start", "eval_time_end", "configure_time_start", "configure_time_end", "aggregate_time_start", "aggregate_time_end"])


    # Add columns
    server_metrics_df["Server time (s)"] = (
        server_metrics_df["Eval time (s)"].fillna(0) +
        server_metrics_df["Configure time (s)"] +
        server_metrics_df["Aggregate time (s)"])

    # Add Server time (s) to job_summaries_df
    merge_cols = ["job_id", "round_number", "stage"]
    job_summaries_df = job_summaries_df.merge(
        server_metrics_df[ merge_cols + ["Server time (s)"] ],
        on=merge_cols, how="left"
    )

    # Add Idle time (s) to job_summaries_df
    # Helper to match server aggregated time start with client end time
    merged_df = job_summaries_df.merge(
        server_metrics_df[ merge_cols + ["aggregate_time_start"] ],
        on=merge_cols, how="left"
    )
    job_summaries_df["Idle time (s)"] = (merged_df["aggregate_time_start"] - merged_df["end_time"]).dt.total_seconds()

    return job_summaries_df, round_metrics_df, hw_metrics_df, server_metrics_df

def collect_job_metrics(job_ids, output_parent_dir, force_collect=False):
    for job_id in job_ids:
        job_metrics_dir = os.path.join(output_parent_dir, "colext_metrics", job_id)

        if os.path.isdir(job_metrics_dir) and not force_collect:
            print(f"Skipping job_id = {job_id} as metrics already collected")
            continue

        command = ["colext_get_metrics", "-j", str(job_id)]
        if force_collect:
            command += ["-f"]

        result = subprocess.run(command, cwd=output_parent_dir, check=True)
        if result.returncode != 0:
            print(f"ERROR: Could not collect job metrics for job_id = {job_id}")

def read_colext_metric_file_as_df(metric_file, job_id_map, job_metrics_parent_dir, date_columns=["start_time", "end_time"]):
    print(f"Reading metrics from {metric_file} and merging as df")
    result_df = []
    for job_id, job_name in job_id_map.items():
        file_path = os.path.join(
            job_metrics_parent_dir,
            "colext_metrics",
            job_id,
            "raw",
            metric_file
        )

        df = pd.read_csv(file_path, parse_dates=date_columns)
        df = df.assign(job_id=job_name)
        result_df.append(df)

    return pd.concat(result_df, ignore_index=True)

def cat_plot(df, plots_dir, name_suffix, header_cols,
                 x_col="dev_type", hue_col="job_id", extra_plot_args={}):
    # Prepare dataset for plotting
    id_vars=["dev_type", "device_name", "job_id", "stage"]
    cols = header_cols + id_vars
    df = df[cols]

    df_long = pd.melt(df, id_vars=id_vars, var_name='metric')

    g = sns.catplot(x=x_col, y="value", hue=hue_col, data=df_long,
                    col="metric",
                    # row="stage",
                    col_wrap=min(len(header_cols), 6),
                    kind="bar", sharey=False, height=3,
                    **extra_plot_args)

    # Increase vertical spacing between rows
    g.figure.subplots_adjust(hspace=0.3)  # default ~0.2, increase as needed

    g.set_axis_labels("", "")
    g.set_titles(col_template="{col_name}", row_template="{row_name}")
    g.figure.autofmt_xdate(rotation=70)

    output_file = os.path.join(plots_dir, f"cat_plot_{name_suffix}")
    g.figure.savefig(f"{output_file}", **OUTPUT_FORMAT_CONFIG)

def plot_totals(round_metrics_df, job_summaries_df, plots_dir):
    orig_order = round_metrics_df["job_id"].unique()

    total_exec_time_df = round_metrics_df.groupby("job_id").apply(
        lambda x: pd.Series({"Execution Time (s)": (x.iloc[-1]["end_time"] - x.iloc[0]["start_time"]).total_seconds()}),
        include_groups=False
    )

    total_energy_df = job_summaries_df.groupby("job_id").apply(
        lambda x: pd.Series({"Total Energy (kJ)": x["Energy in round (J)"].sum() / 1000}),
        include_groups=False
    )

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 5), gridspec_kw={'width_ratios': [1, 1], 'wspace': 0.3})
    sns.barplot(x="job_id", y="Execution Time (s)", data=total_exec_time_df, ax=ax1, order=orig_order)
    sns.barplot(x="job_id", y="Total Energy (kJ)", data=total_energy_df, ax=ax2, order=orig_order)
    fig.autofmt_xdate(rotation=70)

    fig.savefig(os.path.join(plots_dir, "per_job"), **OUTPUT_FORMAT_CONFIG)

def plot_accuracies(round_metrics_df, plots_dir):

    eval_stage_df = round_metrics_df[round_metrics_df["stage"] == "EVAL"].copy()
    eval_stage_df["acc"] = eval_stage_df["dist_accuracy"] * 100

    eval_stage_df["end_time_diff"] = eval_stage_df.groupby("job_id")["end_time"].diff().fillna(pd.Timedelta(seconds=0))
    eval_stage_df["elapsed_time"] = eval_stage_df.groupby("job_id")["end_time_diff"].cumsum().dt.total_seconds()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 5), gridspec_kw={'width_ratios': [1, 1], 'wspace': 0.3})
    job_order = eval_stage_df.groupby("job_id")["acc"].last().sort_values(ascending=False).index
    sns.lineplot(x="round_number", y="acc", hue="job_id", data=eval_stage_df, ax=ax1, legend=False, hue_order=job_order)
    sns.lineplot(x="elapsed_time", y="acc", hue="job_id", data=eval_stage_df, ax=ax2, legend="full", hue_order=job_order)
    ax2.legend(loc='center left', bbox_to_anchor=(1.05, 0.5))

    fig.savefig(os.path.join(plots_dir, "per_job_accuracies"), **OUTPUT_FORMAT_CONFIG)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bench_dir", type=str, help="Directory with benchmark to plot")
    parser.add_argument("-p", "--plots_dir", type=str, default="plots", help="Output dir for plots")
    parser.add_argument("-f", "--force_collect", action="store_true", default=False, help="Force collection of metrics even if dir exists")
    args = parser.parse_args()

    if not os.path.isdir(args.bench_dir):
        print(f"ERROR: Benchmark dir '{args.bench_dir}' does not exist")
        exit(1)

    benchmark_output = os.path.join(args.bench_dir, "output")
    if not os.path.isdir(benchmark_output):
        print(f"ERROR: Benchmark output dir '{benchmark_output}' not found.")
        print("Have you ran the benchmark?")
        exit(1)

    output_job_ids_files = [f for f in os.listdir(benchmark_output) if f.startswith("output_job_id_maps")]
    if len(output_job_ids_files) < 1:
        print(f"ERROR: Could not find file 'output_job_id_maps' in {benchmark_output}")
        print("Have you ran the benchmark?")
        exit(1)

    if len(output_job_ids_files) > 1:
        output_job_ids_files.sort(reverse=True)
        print(f"WARNING: Found more than one file 'output_job_id_maps' in {benchmark_output}. Picking the latest one.")

    output_job_ids_file = os.path.join(benchmark_output, output_job_ids_files[0])
    make_plots(output_job_ids_file, benchmark_output, args)

if __name__ == "__main__":
    main()
