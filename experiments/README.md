# 本地实验目录

`experiments/` 是 StegoPot 的本地实验工作区，用于存放用户编写的实验配置、插件、
数据集引用、运行脚本和实验结果。它与 `stegopot/` 核心包隔离，实验内容通过公开接口
和插件机制调用框架能力。

建议每个实验使用独立目录：

```text
experiments/
  <experiment_id>/
    configs/
    plugins/
    data/
    results/
```

除本说明文件外，该目录中的全部内容均被 Git 忽略，不会上传到仓库。需要公开的通用
组件应整理为正式插件或框架模块，不应直接从本地实验目录提交。
