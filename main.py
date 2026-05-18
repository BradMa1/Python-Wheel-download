#!/usr/bin/env python3
"""
Python Wheel 包批量下载工具 - 优化版
功能：并行下载、进度条、跳过已下载、镜像源、配置文件外置、统计摘要
"""

import subprocess
import os
import re
import sys
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    print("提示: pip install tqdm 可显示进度条")

# ========== 默认配置 ==========
DEFAULT_CONFIG = {
    "target_python": "3.10",
    "target_platform": "manylinux2014_x86_64",
    "max_workers": 8,
    "skip_existing": True,
    "mirrors": [
        "https://pypi.tuna.tsinghua.edu.cn/simple",
        "https://mirrors.aliyun.com/pypi/simple",
        "https://mirrors.cloud.tencent.com/pypi/simple",
        "https://pypi.org/simple"
    ]
}

_lock = threading.Lock()

def get_script_dir():
    return os.path.dirname(os.path.abspath(__file__))

def load_config():
    """从 config.json 加载配置，支持 // 行尾注释，不存在则使用默认配置"""
    script_dir = get_script_dir()
    config_path = os.path.join(script_dir, "config.json")

    if os.path.isfile(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            # 去掉 // 注释（仅在引号外，即不在字符串内）
            result = []
            in_string = False
            i = 0
            while i < len(content):
                c = content[i]
                if c == '"' and (i == 0 or content[i-1] != '\\'):
                    in_string = not in_string
                    result.append(c)
                elif c == '/' and i + 1 < len(content) and content[i+1] == '/' and not in_string:
                    # 跳过到行尾
                    while i < len(content) and content[i] != '\n':
                        i += 1
                    continue
                else:
                    result.append(c)
                i += 1
            user_config = json.loads(''.join(result))
            # 合并默认配置与用户配置
            config = DEFAULT_CONFIG.copy()
            config.update(user_config)
            print(f"[配置] 已加载: {config_path}")
            return config
        except Exception as e:
            print(f"[警告] 配置文件读取失败 ({e})，使用默认配置")

    return DEFAULT_CONFIG

def save_default_config():
    """首次运行生成带注释的配置文件"""
    script_dir = get_script_dir()
    config_path = os.path.join(script_dir, "config.json")

    if os.path.isfile(config_path):
        return  # 已存在不覆盖

    with open(config_path, 'w', encoding='utf-8') as f:
        f.write("""{
  // =============================================
  //  Python Wheel 包下载工具 - 配置文件
  // =============================================

  // 【目标 Python 版本】填写目标机器的 Python 版本号
  // 查看方法：在目标机器上运行 python3 --version
  "target_python": "3.10",

  // 【目标平台/系统】填写目标机器的操作系统和架构
  // 常见值：
  //   manylinux2014_x86_64  → Linux x86_64 (最常见，腾讯云/阿里云等)
  //   manylinux2014_aarch64 → Linux ARM64 (树莓派、部分云服务器)
  //   macosx_11_0_x86_64    → macOS Intel
  //   macosx_11_0_arm64     → macOS M1/M2/M3
  //   win_amd64              → Windows x86_64
  "target_platform": "manylinux2014_x86_64",

  // 【并行下载线程数】同时下载多少个包，数字越大越快，但可能占带宽，一般 4~16
  "max_workers": 8,

  // 【是否跳过已下载的包】true=目录下已有的包跳过节省时间（推荐），false=每次重新下
  "skip_existing": true,

  // 【PyPI 镜像源】按顺序尝试，成功即止，国内机器保留前三个即可
  // 如果目标机器在国外，只保留最后一个官方源：["https://pypi.org/simple"]
  "mirrors": [
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://mirrors.aliyun.com/pypi/simple",
    "https://mirrors.cloud.tencent.com/pypi/simple",
    "https://pypi.org/simple"
  ]
}
""")

def find_package_list_file():
    script_dir = get_script_dir()
    print(f"脚本所在目录: {script_dir}")

    candidates = [
        "pip_list.txt", "requirements.txt", "packages.txt",
        "list.txt", "pip-list.txt", "pip_freeze.txt", "req.txt"
    ]
    for name in candidates:
        full = os.path.join(script_dir, name)
        if os.path.isfile(full):
            return full

    all_files = [f for f in os.listdir(script_dir)
                 if os.path.isfile(os.path.join(script_dir, f))]
    if not all_files:
        print("错误：脚本所在目录下没有任何文件。")
        return None

    print("在脚本所在目录下找到以下文件：")
    for i, f in enumerate(all_files, 1):
        print(f"  {i}. {f}")

    while True:
        choice = input("请选择包列表文件编号 (1-{}) 或直接输入文件名: ".format(len(all_files))).strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(all_files):
                return os.path.join(script_dir, all_files[idx])
        else:
            full_path = os.path.join(script_dir, choice)
            if os.path.isfile(full_path):
                return full_path
        print("选择无效，请重新输入。")

def parse_pip_list(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    packages = []
    freeze_mode = any('==' in line and not line.startswith('-') for line in lines)

    if freeze_mode:
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '==' in line:
                name, version = line.split('==', 1)
                packages.append((name.strip(), version.strip()))
    else:
        for line in lines:
            line = line.strip()
            if not line or line.startswith('-') or line.startswith('Package'):
                continue
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                version = re.sub(r'[\(\)]', '', parts[1])
                packages.append((name, version))
    return packages

def get_existing_wheels(download_dir):
    """获取已下载的包名列表"""
    existing = set()
    if os.path.isdir(download_dir):
        for f in os.listdir(download_dir):
            if f.endswith('.whl') or f.endswith('.tar.gz') or f.endswith('.zip'):
                # 提取包名 (格式: name-version.whl)
                match = re.match(r'([a-zA-Z0-9_\-]+)-', f)
                if match:
                    existing.add(match.group(1))
    return existing

def get_dir_size(download_dir):
    """计算目录大小 (MB)"""
    total = 0
    if os.path.isdir(download_dir):
        for f in os.listdir(download_dir):
            fp = os.path.join(download_dir, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total / (1024 * 1024)

def download_single_package(name, version, download_dir, config, pbar=None):
    """下载单个包，返回 (name, version, success, msg)"""
    spec = f"{name}=={version}"
    result = {"name": name, "version": version, "success": False, "msg": ""}

    # 检查是否跳过已下载
    if config.get("skip_existing", True):
        existing = get_existing_wheels(download_dir)
        if name.lower() in {p.lower() for p in existing}:
            result["success"] = True
            result["msg"] = "跳过 (已存在)"
            if pbar:
                pbar.update(1)
            return result

    # 逐个镜像尝试
    mirrors = config.get("mirrors", [])
    errors = []

    for attempt in range(2):  # 最多重试2次
        for mirror in mirrors:
            cmd = [
                sys.executable, "-m", "pip", "download",
                "-d", download_dir,
                "--index-url", mirror,
                "--no-deps",
                spec
            ]

            # 首次尝试加平台限制
            if attempt == 0:
                cmd.extend(["--platform", config["target_platform"]])
                cmd.extend(["--python-version", config["target_python"]])
                cmd.extend(["--only-binary=:all:"])

            try:
                proc = subprocess.run(
                    cmd, check=True,
                    capture_output=True, text=True,
                    timeout=120
                )
                result["success"] = True
                result["msg"] = f"成功 (镜像: {mirror.split('//')[1].split('/')[0]})"
                if pbar:
                    pbar.update(1)
                return result
            except subprocess.CalledProcessError as e:
                errors.append(f"{mirror}: {e.stderr[:100] if e.stderr else 'unknown'}")
            except subprocess.TimeoutExpired:
                errors.append(f"{mirror}: 超时")
            except Exception as e:
                errors.append(f"{mirror}: {e}")

        # 第二次尝试：源码包 fallback
        if attempt == 0:
            # 如果平台 wheel 全部失败，换源码模式
            pass

    result["msg"] = " | ".join(errors[:2])
    if pbar:
        pbar.update(1)
    return result

def download_packages(packages, download_dir, config):
    """并行下载所有包"""
    os.makedirs(download_dir, exist_ok=True)

    max_workers = config.get("max_workers", 8)
    print(f"\n{'='*50}")
    print(f"[下载配置]")
    print(f"  目标平台: {config['target_platform']}")
    print(f"  Python 版本: {config['target_python']}")
    print(f"  并行线程: {max_workers}")
    print(f"  跳过已下载: {config.get('skip_existing', True)}")
    print(f"  镜像数量: {len(config.get('mirrors', []))}")
    print(f"{'='*50}\n")

    total = len(packages)
    results = {"success": 0, "skip": 0, "failed": 0, "failed_list": []}
    start_time = time.time()

    # 进度条
    if HAS_TQDM:
        pbar = tqdm(total=total, desc="下载进度", unit="包", ncols=80)
    else:
        pbar = None

    def worker(args):
        return download_single_package(*args, download_dir, config, pbar)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(worker, (name, version)): (name, version)
            for name, version in packages
        }

        for future in as_completed(futures):
            result = future.result()
            if result["success"]:
                if "跳过" in result["msg"]:
                    results["skip"] += 1
                else:
                    results["success"] += 1
            else:
                results["failed"] += 1
                results["failed_list"].append(
                    f"{result['name']}=={result['version']}: {result['msg']}"
                )

    if pbar:
        pbar.close()

    elapsed = time.time() - start_time

    # 统计摘要
    print(f"\n{'='*50}")
    print(f"[下载统计]")
    print(f"  总计: {total} 包")
    print(f"  成功: {results['success']} 包")
    print(f"  跳过: {results['skip']} 包")
    print(f"  失败: {results['failed']} 包")
    print(f"  耗时: {elapsed:.1f} 秒")
    print(f"  速度: {total/elapsed:.1f} 包/秒" if elapsed > 0 else "")
    dir_size = get_dir_size(download_dir)
    print(f"  下载目录大小: {dir_size:.2f} MB")
    print(f"  保存位置: {os.path.abspath(download_dir)}")
    print(f"{'='*50}")

    # 失败报告
    if results["failed_list"]:
        failed_file = os.path.join(get_script_dir(), "failed_packages.txt")
        with open(failed_file, 'w', encoding='utf-8') as f:
            f.write("# 下载失败的包 (可手动重试或检查版本兼容性)\n")
            for item in results["failed_list"]:
                name_ver = item.split(":")[0]
                f.write(f"{name_ver}\n")

        print(f"\n⚠️  {results['failed']} 个包下载失败")
        print(f"   详情已保存到: {failed_file}")
        print(f"\n失败详情:")
        for item in results["failed_list"]:
            print(f"  - {item}")
    else:
        print(f"\n✅ 所有包处理完成，没有失败项")

    return results

def main():
    script_dir = get_script_dir()
    os.chdir(script_dir)
    print(f"工作目录: {script_dir}")

    # 加载配置
    config = load_config()

    # 查找包列表文件
    list_file = find_package_list_file()
    if not list_file:
        print("没有选择任何包列表文件，程序退出。")
        return

    print(f"使用包列表文件: {list_file}")
    packages = parse_pip_list(list_file)
    if not packages:
        print("没有解析到任何包，请检查文件格式。")
        return

    print(f"解析到 {len(packages)} 个包")

    download_dir = os.path.join(script_dir, "packages_download")
    download_packages(packages, download_dir, config)

if __name__ == "__main__":
    main()
