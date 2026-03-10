from Code.local_models.local_kbc import main


def run_command(*args) -> str:
    try:
        return main(*args)
    except Exception as e:
        return str(e)
