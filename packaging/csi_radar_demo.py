"""Точка входа для CSI_radar_demo.exe — то же, что csi_radar.py --demo."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.argv += ["--demo"]

from csi_radar import main  # noqa: E402

main()
