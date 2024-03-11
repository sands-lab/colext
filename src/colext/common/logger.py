# Inspired by flwrs log:
# https://github.com/adap/flower/blob/a3111ed48d7119921a5b7296922f17f1e9d1fcef/src/py/flwr/common/logger.py
# Useful: https://stackoverflow.com/a/43794480
import logging

DEFAULT_FORMATTER = logging.Formatter(
    "%(levelname)s %(name)s %(asctime)s | %(filename)s:%(lineno)d | %(message)s"
)

LOGGER_NAME = "COLEXT"
TESTBED_LOGGER = logging.getLogger(LOGGER_NAME)
TESTBED_LOGGER.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setFormatter(DEFAULT_FORMATTER)
TESTBED_LOGGER.addHandler(console_handler)

log = TESTBED_LOGGER