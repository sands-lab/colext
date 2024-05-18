import time

import Monsoon.HVPM as HVPM
import Monsoon.sampleEngine as sampleEngine

Mon = HVPM.Monsoon()
Mon.setup_usb()

Mon.setPowerupTime(20)
Mon.setPowerUpCurrentLimit(4.6)
Mon.setRunTimeCurrentLimit(4.6)
Mon.setVout(4.2)

engine = sampleEngine.SampleEngine(Mon)

engine.enableChannel(sampleEngine.channels.MainCurrent)
engine.enableChannel(sampleEngine.channels.MainVoltage)

engine.disableCSVOutput()
ts = time.time()
engine.startSampling(sampleEngine.triggers.SAMPLECOUNT_INFINITE)
samples = engine.getSamples()