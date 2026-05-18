# Python Wheel 包批量下载工具

批量下载 Python 包为 wheel 文件，支持并行下载、多镜像切换、跳过已下载包，适合离线环境部署。

---

## 工作流程

```
步骤 1: 有网的机器
  pip list > pip_list.txt          # 导出包列表
  python main.py                    # 下载包到 packages_download/
  # 失败的包 → failed_packages.txt

步骤 2: 目标机器（离线）
  把整个目录拷贝过去
  ./install.sh                     # 一键安装
```

---

## 快速开始

### 步骤 1：导出包列表

在**有网**的机器上运行：

```bash
pip list > pip_list.txt
```

### 步骤 2：修改配置

根据**目标机器**的系统环境，修改 `config.json`：

| 配置项 | 是否需改 | 说明 |
|--------|---------|------|
| `target_python` | **需要** | 目标机器的 Python 版本 |
| `target_platform` | **需要** | 目标机器的系统/架构 |
| `max_workers` | 一般不改 | 并行下载线程数，一般 4~16 |
| `skip_existing` | 一般不改 | true=跳过已下载的包 |
| `mirrors` | 一般不改 | 镜像源列表，按顺序尝试 |

**如何填写 target_platform？** 在目标机器上运行 `uname -m`：

| 运行结果 | 填入的值 |
|---------|---------|
| `x86_64`（Linux） | `manylinux2014_x86_64` |
| `aarch64`（Linux） | `manylinux2014_aarch64` |
| `x86_64`（macOS Intel） | `macosx_11_0_x86_64` |
| `arm64`（macOS M1/M2） | `macosx_11_0_arm64` |
| Windows | `win_amd64` |

**如何填写 target_python？** 在目标机器上运行 `python3 --version`，把版本号填入即可。

### 步骤 3：下载包

```bash
pip install tqdm          # 可选，显示进度条
python main.py
```

脚本会自动读取 `pip_list.txt`，按 config.json 配置下载，失败包跳过并记录。

### 步骤 4：离线安装

把整个目录拷贝到目标机器：

```bash
chmod +x install.sh
./install.sh
```

---

## 环境要求

- Python 3.7+
- pip

---

## 常见问题

### Q: 进度条不显示？
A: 运行 `pip install tqdm`

### Q: 某些包下载失败？
A: 正常，部分包没有对应平台的 wheel 文件。失败的包会记录在 `failed_packages.txt`。

### Q: 目标机器是 Windows？
A: 把 `target_platform` 改为 `win_amd64`，`mirrors` 只保留 `["https://pypi.org/simple"]`

### Q: 目标机器在国外？
A: 把 `mirrors` 改为 `["https://pypi.org/simple"]`

---

## 目录结构

```
├── main.py                  # 下载脚本
├── install.sh               # 安装脚本
├── config.json              # 配置文件（支持 // 注释）
├── pip_list.txt             # 包列表（用户导入）
├── failed_packages.txt      # 失败包列表（自动生成）
└── packages_download/        # 下载的包（自动创建）
    ├── numpy-1.24.0-cp310-cp310-manylinux.whl
    └── ...
```

---

## License

MIT
