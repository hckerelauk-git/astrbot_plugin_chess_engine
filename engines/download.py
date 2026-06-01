import platform
import re
import shutil
import subprocess
from pathlib import Path

import aiohttp

# Pikafish GitHub Releases 地址
PIKAFISH_REPO = "official-pikafish/Pikafish"
PIKAFISH_LATEST_URL = f"https://api.github.com/repos/{PIKAFISH_REPO}/releases/latest"


def get_platform_info() -> tuple[str, str]:
    """获取当前系统平台信息，返回 (系统名, 可执行文件后缀)"""
    system = platform.system().lower()
    if system == "windows":
        return "windows", ".exe"
    elif system == "linux":
        return "linux", ""
    elif system == "darwin":
        return "mac", ""
    return system, ""


def get_arch_tag() -> str:
    """获取 CPU 架构标签"""
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x86-64"
    elif machine in ("aarch64", "arm64"):
        return "arm64"
    return "x86-64"


def get_pikafish_filename() -> str:
    """获取 Pikafish 可执行文件名"""
    system, ext = get_platform_info()
    return f"pikafish{ext}"


def get_pikafish_dir() -> Path:
    """获取 Pikafish 存放目录"""
    plugin_dir = Path(__file__).parent.parent
    bin_dir = plugin_dir / "bin" / "pikafish"
    bin_dir.mkdir(parents=True, exist_ok=True)
    return bin_dir


def find_pikafish_binary() -> Path | None:
    """查找已安装的 Pikafish 二进制，递归搜索 bin/pikafish 目录"""
    bin_dir = get_pikafish_dir()
    filename = get_pikafish_filename()

    # 先直接查
    direct = bin_dir / filename
    if direct.exists():
        return direct

    # 递归搜索
    for f in bin_dir.rglob(filename):
        if f.is_file():
            return f
    return None


async def get_latest_release_info() -> dict:
    """获取 Pikafish 最新版本信息"""
    async with aiohttp.ClientSession() as session:
        async with session.get(PIKAFISH_LATEST_URL) as resp:
            if resp.status != 200:
                raise RuntimeError(f"获取版本信息失败: HTTP {resp.status}")
            return await resp.json()


def get_asset_info(release_info: dict) -> tuple[str, str]:
    """
    获取发布包的下载 URL 和文件名。
    Pikafish 只有一个包，包含所有平台二进制。
    """
    assets = release_info.get("assets", [])
    if not assets:
        raise RuntimeError("发布页无可用下载包")

    asset = assets[0]
    return asset.get("browser_download_url", ""), asset.get("name", "")


async def download_pikafish() -> Path:
    """下载并解压 Pikafish，返回可执行文件路径"""
    bin_dir = get_pikafish_dir()
    filename = get_pikafish_filename()

    # 已安装则跳过
    existing = find_pikafish_binary()
    if existing:
        return existing

    release_info = await get_latest_release_info()
    download_url, asset_name = get_asset_info(release_info)
    archive_path = bin_dir / asset_name

    # 下载
    async with aiohttp.ClientSession() as session:
        async with session.get(download_url) as resp:
            if resp.status != 200:
                raise RuntimeError(f"下载失败: HTTP {resp.status}")
            with open(archive_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(65536):
                    f.write(chunk)

    # 解压 .7z 文件
    _extract_archive(archive_path, bin_dir)

    # 清理压缩包
    archive_path.unlink(missing_ok=True)

    # 再次查找
    result = find_pikafish_binary()
    if result:
        return result

    raise RuntimeError(
        f"解压后未找到 {filename}，请检查包内结构并手动指定 pikafish_path"
    )


def _extract_archive(archive_path: Path, dest_dir: Path):
    """解压 .7z/.zip 文件到目标目录"""
    suffix = archive_path.suffix.lower()

    if suffix == ".7z":
        _extract_7z(archive_path, dest_dir)
    elif suffix == ".zip":
        _extract_zip(archive_path, dest_dir)
    else:
        raise RuntimeError(f"不支持的压缩格式: {suffix}")


def _extract_7z(archive_path: Path, dest_dir: Path):
    """用系统 7z 命令解压"""
    # 先找系统 7z
    seven_zip = shutil.which("7z") or shutil.which("7z.exe") or shutil.which("7za")

    if seven_zip:
        result = subprocess.run(
            [seven_zip, "x", str(archive_path), f"-o{str(dest_dir)}", "-y"],
            capture_output=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"7z 解压失败: {result.stderr.decode('utf-8', 'ignore')[:200]}")
        _fix_nested_extraction(dest_dir)
        return

    # 没有 7z，尝试 py7zr
    try:
        import py7zr
        with py7zr.SevenZipFile(archive_path, mode="r") as archive:
            archive.extractall(path=dest_dir)
        _fix_nested_extraction(dest_dir)
        return
    except ImportError:
        pass

    # 都没有，尝试用 PowerShell（Windows）
    if platform.system().lower() == "windows":
        result = subprocess.run(
            [
                "powershell", "-Command",
                f"Expand-7Zip -ArchivePath '{archive_path}' -DestinationPath '{dest_dir}' -Force"
            ],
            capture_output=True,
            timeout=120,
        )
        if result.returncode == 0:
            _fix_nested_extraction(dest_dir)
            return

    raise RuntimeError(
        "需要 7z 解压工具，请安装:\n"
        "  Windows: winget install 7zip.7zip\n"
        "  Linux: apt install p7zip-full\n"
        "  或 pip install py7zr"
    )


def _extract_zip(archive_path: Path, dest_dir: Path):
    """用 Python zipfile 解压"""
    import zipfile
    with zipfile.ZipFile(archive_path, "r") as zf:
        zf.extractall(dest_dir)
    _fix_nested_extraction(dest_dir)


def _fix_nested_extraction(dest_dir: Path):
    """
    有些包解压后会在子目录里。
    把深层文件移到根目录。
    """
    # 找目标文件名
    _, ext = get_platform_info()
    target = f"pikafish{ext}"

    # 如果根目录已有，不处理
    if (dest_dir / target).exists():
        return

    # 递归查找
    for f in dest_dir.rglob(target):
        # 移到根目录
        dest = dest_dir / target
        shutil.move(str(f), str(dest))
        # 删除空子目录
        parent = f.parent
        while parent != dest_dir:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
        return