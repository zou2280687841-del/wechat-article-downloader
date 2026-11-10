import sys
from pathlib import Path

APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
if getattr(sys, 'frozen', False) and APP_DIR.name == 'runtime':
    APP_DIR = APP_DIR.parent

if __name__ == '__main__':
    if '--smoke-test' in sys.argv:
        from wxbackup.smoke import run_smoke
        run_smoke(Path(sys.argv[sys.argv.index('--smoke-test')+1]))
        raise SystemExit(0)
    from wxbackup.gui import run
    run(APP_DIR)
