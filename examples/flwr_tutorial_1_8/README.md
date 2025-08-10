## Running this example
The commands below assume that the working directory is set to this folder.
Run `cd` into this folder before executing the commands.


### CoLExT Deployment
```
colext_launch_job
# Uses colext_config.yaml by default

# If using a different config file:
colext_launch_job -c <config_file>
```

### Local deployemnt / Outside of CoLExT environment
1. Install the app's extra dependencies.
```bash
pip install -r requirements.txt
```

2. Uses the CoLExT launcher to run a local debug job.
CoLExT env variables (e.g. COLEXT_CLIENT_ID and COLEXT_N_CLIENTS) will still be available.
```bash
colext_launch_job -d
```
