from .sbc_deployer.sbc_deployer import SBCDeployer
from .local_py_deployer.local_deployer import LocalDeployer

def get_deployer(deployer_type="sbc"):
    if "sbc" == deployer_type:
        deployer = SBCDeployer
    elif "android" == deployer_type:
        raise NotImplementedError
    elif "local_py" == deployer_type:
        deployer = LocalDeployer
    else:
        raise NotImplementedError

    return deployer
