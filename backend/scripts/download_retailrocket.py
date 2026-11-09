"""Download the Retailrocket ecommerce clickstream (Kaggle: retailrocket/ecommerce-dataset)."""

import shutil
import subprocess
import sys
from pathlib import Path

from app.core.config import settings

OUT = settings.raw_dir / "retailrocket"


def main() -> int:
    if (OUT / "events.csv").exists():
        print(f"✓ Retailrocket already present in {OUT}")
        return 0
    creds = Path.home() / ".kaggle" / "kaggle.json"
    if not creds.exists():
        print("Kaggle credentials not found (~/.kaggle/kaggle.json).")
        print("  1. kaggle.com -> Settings -> API -> Create New Token  (downloads kaggle.json)")
        print(
            "  2. mkdir -p ~/.kaggle && mv ~/Downloads/kaggle.json ~/.kaggle/ && chmod 600 ~/.kaggle/kaggle.json"
        )
        print("  3. make retailrocket")
        return 0
    kaggle = shutil.which("kaggle") or str(Path(sys.executable).parent / "kaggle")
    OUT.mkdir(parents=True, exist_ok=True)
    print("↓ downloading retailrocket/ecommerce-dataset (~300 MB) ...", flush=True)
    subprocess.run(
        [kaggle, "datasets", "download", "-d", "retailrocket/ecommerce-dataset", "-p", str(OUT), "--unzip"],
        check=True,
    )
    print(f"Retailrocket ready in {OUT}: {[p.name for p in OUT.iterdir()]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
