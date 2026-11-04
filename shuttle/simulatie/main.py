"""Start vanuit shuttle: python -m simulatie (of python simulatie/main.py)."""
import sys
from pathlib import Path

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        print('Installeer eerst de grafische pakketten met:')
        print('python -m pip install -r requirements-sim.txt')
        return 1
    from simulatie.venster import Venster
    app=QApplication.instance() or QApplication(sys.argv)
    app.setStyle('Fusion')
    venster=Venster();venster.show()
    return app.exec()


if __name__=='__main__':
    raise SystemExit(main())
