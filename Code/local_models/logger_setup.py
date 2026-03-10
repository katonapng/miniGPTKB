import logging

logger = logging.getLogger('gui_logger')
logger.setLevel(logging.DEBUG)


if not logger.handlers:
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s: %(message)s'
    )

    file_handler = logging.FileHandler("kbc_extraction.log")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
