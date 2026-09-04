"""支持 python -m stegopot 的统一入口。"""

from stegopot.bootstrap.experiments.cli import main

if __name__ == "__main__":
  raise SystemExit(main())
