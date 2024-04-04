import os
import sys

def get_colext_env_var_or_exit(env_var_name):
    colext_env_var = os.getenv(env_var_name)
    if colext_env_var is None:
        print(f"Expected env variable '{colext_env_var}' to exist inside CoLExT environment but it is not defined. Exiting.") 
        sys.exit(1)
    else:
        return colext_env_var