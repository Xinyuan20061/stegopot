# 用户配置目录

将自己编写的 `.yaml`、`.yml` 或 `.json` 配置放在这里，可按主题建立子目录。
交付时不附带任何实验配置。格式与参数见 [配置指南](../docs/usage.md)。

在工作区根目录使用：

```powershell
python -m stegopot list
python -m stegopot validate <配置名称>
python -m stegopot run <配置名称>
```

只有一份配置时可省略名称；多份或同名不同后缀时必须明确指定文件。
模型密钥放在工作区 `.env` 或进程环境中，不要写入配置。
结果默认写入工作区 `outputs/`，不写入本目录。

本仓库默认忽略用户的 JSON/YAML 配置，防止误提交研究材料。
第三方需要公开配置时，请先审查内容，再自行选择版本控制范围。
