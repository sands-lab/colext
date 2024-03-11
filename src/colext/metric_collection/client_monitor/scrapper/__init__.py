import os 

uname_release = os.uname().release
if "tegra" in uname_release:
    try: 
        from jtop import jtop
    except ImportError:
        raise ImportError("Jetson device detected -> expected jtop package to be installed but it could not be found.")
