# StegoPot Collusion

独立的指令式共享协议实验扩展。它提供场景计划、专用角色、信道及中央评分；
所有运行、审计、模型调用和配对重放由宿主统一管理。

在仓库根目录安装：`python -m pip install -e extensions/stegopot-collusion`。
离线运行：`python -m stegopot run experiments/collusion/offline.yaml`。
真实模型配置另需安装供应商扩展并显式加载 .env，参见根 README。

人工协议与规则夹具不代表自发行为。评价不实现隐写检测算法，
不能把观察者未猜中视为不可检测证明。
