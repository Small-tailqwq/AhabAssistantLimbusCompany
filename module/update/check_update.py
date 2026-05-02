import hashlib
import os  # 导入os模块以便操作文件路径
import re
import shutil
import subprocess
from enum import Enum
from threading import Thread

import requests  # 导入requests模块，用于发送HTTP请求
from markdown_it import MarkdownIt
from packaging.version import parse
from PySide6.QtCore import QT_TRANSLATE_NOOP, Qt, QThread, Signal
from qfluentwidgets import InfoBarPosition

from app import mediator
from app.card.messagebox_custom import BaseInfoBar, MessageBoxUpdate
from module.config import cfg
from module.decorator.decorator import begin_and_finish_time_log
from module.logger import log

md_renderer = MarkdownIt("gfm-like", {"html": True})


def _normalize_version(v: str) -> str:
    """将 canary 版本号（X.Y.Z-canary[.N]）转换为 PEP 440 兼容格式（X.Y.ZdevN）。"""
    return re.sub(r"-canary[\.-]?", "dev", v)


class UpdateStatus(Enum):
    """
    定义更新状态的枚举类

    该枚举类用于表示更新操作的三种可能结果状态：
    - SUCCESS 表示更新操作成功
    - UPDATE_AVAILABLE 表示有可用的更新
    - FAILURE 表示更新操作失败
    """

    SUCCESS = 1
    UPDATE_AVAILABLE = 2
    FAILURE = 0


class UpdateThread(QThread):
    """
    更新线程类，用于在后台检查和处理软件更新。
    该类继承自 QThread，使用 Qt 的信号机制来通知 GUI 线程更新状态。
    """

    # 定义更新信号，用于通知主线程更新状态
    updateSignal = Signal(UpdateStatus)

    def __init__(self, timeout, flag):
        """
        初始化更新线程。

        参数:
        timeout -- 超时时间（秒）
        flag -- 标志位，用于控制是否执行检查更新
        """
        super().__init__()
        self.timeout = timeout  # 超时时间
        self.flag = flag  # 标志位，用于控制是否执行检查更新
        self.error_msg = ""  # 错误信息

        self.repo = "AhabAssistantLimbusCompany"
        # 金丝雀通道：配置指定 或 版本号包含 -canary 时自动切换
        self._canary = cfg.update_channel == "canary" or "-canary" in cfg.version
        self.user = "Small-tailqwq" if self._canary else "KIYI671"
        self.new_version = ""

    def run(self) -> None:
        """
        更新线程的主逻辑。
        检查是否有新版本，如果有，则发送更新可用信号；否则发送成功信号。
        """
        try:
            # 如果标志位为 False 且配置中的检查更新标志也为 False，则直接返回
            if self.flag and not cfg.get_value("check_update"):
                return

            data = self.check_update_info_github()
            version = data["tag_name"]
            self.new_version = version
            content = self.remove_images_from_markdown(data["body"])
            self._cached_assets_url = self.get_download_url_from_assets(data["assets"])

            # 如果没有可用的下载 URL，则发送成功信号并返回
            if self._cached_assets_url is None:
                self.updateSignal.emit(UpdateStatus.SUCCESS)
                return

            # 比较当前版本和最新版本，如果最新版本更高，则准备更新
            if parse(_normalize_version(version.lstrip("Vv"))) > parse(_normalize_version(cfg.version.lstrip("Vv"))):
                self.title = self.tr("发现新版本：{Old_version} ——> {New_version}\n更新日志:").format(
                    Old_version=cfg.version, New_version=version
                )
                self.content = "<style>a {color: #586f50; font-weight: bold;}</style>" + md_renderer.render(content)
                self.updateSignal.emit(UpdateStatus.UPDATE_AVAILABLE)
            else:
                # 如果没有新版本，则发送成功信号
                self.updateSignal.emit(UpdateStatus.SUCCESS)
        except Exception as e:
            # 异常处理，发送失败信号
            log.error(f"检查更新失败:{e}")
            self.updateSignal.emit(UpdateStatus.FAILURE)

    @property
    def _github_use_releases_list(self):
        """金丝雀通道始终走 releases 列表（含 prerelease），稳定版按配置决定"""
        return self._canary or cfg.update_prerelease_enable

    def check_update_info_github(self):
        """
        从 GitHub 获取最新发布版本的信息。

        返回:
        最新发布版本的信息（JSON 格式）
        """
        if self._github_use_releases_list:
            response = requests.get(
                f"https://api.github.com/repos/{self.user}/{self.repo}/releases",
                timeout=10,
                headers=cfg.useragent,
            )
        else:
            response = requests.get(
                f"https://api.github.com/repos/{self.user}/{self.repo}/releases/latest",
                timeout=10,
                headers=cfg.useragent,
            )
        response.raise_for_status()
        return response.json()[0] if self._github_use_releases_list else response.json()

    def remove_images_from_markdown(self, markdown_content):
        """
        从 Markdown 内容中移除图片。

        参数:
        markdown_content -- Markdown 格式的文本

        返回:
        移除图片后的 Markdown 文本
        """
        img_pattern = re.compile(r"!\[.*?\]\(.*?\)")
        return img_pattern.sub("", markdown_content)

    def get_download_url_from_assets(self, assets):
        """
        从资产列表中获取 .7z 文件的下载 URL。

        参数:
        assets -- 资产列表（JSON 格式）

        返回:
        .7z 文件的下载 URL，如果没有找到则返回 None
        """
        for asset in assets:
            if asset["name"].endswith(".7z"):
                return asset["browser_download_url"]
        return None

    def get_assets_url(self):
        if getattr(self, "_cached_assets_url", None):
            return self._cached_assets_url
        try:
            return self._get_assets_url_github()
        except Exception as e:
            log.error(f"更新失败:{e}")
            self.updateSignal.emit(UpdateStatus.FAILURE)

    def _get_assets_url_github(self):
        if self._github_use_releases_list:
            response = requests.get(
                f"https://api.github.com/repos/{self.user}/{self.repo}/releases",
                timeout=10,
                headers=cfg.useragent,
            )
        else:
            response = requests.get(
                f"https://api.github.com/repos/{self.user}/{self.repo}/releases/latest",
                timeout=10,
                headers=cfg.useragent,
            )
        response.raise_for_status()
        data = response.json()[0] if self._github_use_releases_list else response.json()
        assets_url = self.get_download_url_from_assets(data["assets"])
        if assets_url is None:
            log.error("更新失败：未找到可用的下载资产")
            self.updateSignal.emit(UpdateStatus.FAILURE)
            return
        return assets_url


@begin_and_finish_time_log(task_name="检查更新")
def check_update(self, timeout=5, flag=False):
    """检查更新功能函数。
    :param timeout: 超时时间，默认为5秒。
    :param flag: 更新检查的标志，默认为False。
    此函数主要用于启动一个更新线程，并监听更新状态。
    """

    def handler_update(status):
        """
        更新处理函数，根据不同的更新状态执行不同的操作。
        :param status: 更新状态。
        """
        if status == UpdateStatus.UPDATE_AVAILABLE:
            # 当有可用更新时，创建一个消息框对象并显示详细信息
            messages_box = MessageBoxUpdate(self.update_thread.title, self.update_thread.content, self.window())
            if messages_box.exec():
                # 如果用户确认更新，则从指定的URL下载更新资源
                assets_url = self.update_thread.get_assets_url()
                if assets_url:
                    start_update_thread(assets_url)
        elif status == UpdateStatus.SUCCESS:
            # 显示当前为最新版本的信息
            bar = BaseInfoBar.success(
                title=QT_TRANSLATE_NOOP("BaseInfoBar", "当前是最新版本(＾∀＾●)"),
                content="",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=1000,
                parent=self,
            )
        else:
            # 显示检查更新失败的信息
            bar = BaseInfoBar.warning(
                title=QT_TRANSLATE_NOOP("BaseInfoBar", "检测更新失败(╥╯﹏╰╥)"),
                content=self.update_thread.error_msg,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )

    # 创建一个更新线程实例
    self.update_thread = UpdateThread(timeout, flag)
    # 将更新处理函数连接到更新线程的信号
    self.update_thread.updateSignal.connect(handler_update)
    # 启动更新线程
    self.update_thread.start()


def is_valid_url(url):
    """
    判断给定的URL是否有效。
    该函数通过解析URL的组成部分来验证其有效性。一个有效的URL应该包含方案（scheme）和网络位置（netloc）。
    参数:
    url (str): 待验证的URL。
    返回:
    bool: 如果URL有效则返回True，否则返回False。
    """
    from urllib.parse import urlparse

    try:
        # 解析URL
        result = urlparse(url)
        # 检查URL是否包含必要的组成部分
        return all([result.scheme, result.netloc])
    except Exception:
        # 如果解析过程中出现异常，说明URL无效
        return False


def update(assets_url):
    """
    从给定的URL下载更新文件到本地。
    :param assets_url : 更新文件的URL。
    """
    # 检查URL是否有效
    if not is_valid_url(assets_url):
        log.error("更新失败：获取的URL无效 ")
        return

    # 提取文件名
    file_name = assets_url.split("/")[-1]
    if "7z" not in file_name:
        file_name = "AALC.zip"
    elif "AALC" in file_name:
        file_name = "AALC.7z"
    log.info(f"正在下载 {file_name} ...")

    try:
        # 发起HTTP请求获取文件
        response = requests.get(assets_url, stream=True, timeout=10)
        response.raise_for_status()  # 检查 HTTP 请求是否成功

        # 获取文件总大小
        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0

        # 创建保存临时文件的目录
        os.makedirs("update_temp", exist_ok=True)
        # 构建保存文件的完整路径
        file_path = os.path.join("update_temp", file_name)

        with requests.get(assets_url, stream=True) as r:
            with open(file_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        progress = int(downloaded / total_size * 100)
                        mediator.update_progress.emit(progress)

        log.info("下载进度100%")

        # 下载完成 → 校验 SHA256（旧版本无 hash 文件时跳过）
        try:
            hash_url = assets_url + ".sha256"
            hash_resp = requests.get(hash_url, timeout=10)
            hash_resp.raise_for_status()
            expected_hash = hash_resp.text.strip()

            actual_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    actual_hash.update(chunk)

            if actual_hash.hexdigest() != expected_hash:
                log.error(f"下载文件哈希校验失败: 期望 {expected_hash}, 实际 {actual_hash.hexdigest()}")
                return
            log.info("下载文件哈希校验通过")
        except requests.exceptions.RequestException:
            log.warning("无法获取哈希文件（旧版本或无 hash 文件），跳过校验")

        if "OCR" in file_name:
            exe_path = os.path.abspath("./assets/binary/7za.exe")
            download_file_path = os.path.join("./update_temp", file_name)
            destination = os.path.abspath("./3rdparty")
            try:
                if os.path.exists(exe_path):
                    subprocess.run(
                        [exe_path, "x", download_file_path, f"-o{destination}", "-aoa"],
                        check=True,
                    )
                else:
                    shutil.unpack_archive(download_file_path, destination)
                log.info("OCR解压完成，请重启AALC")
                return True
            except Exception:
                input("解压失败，按回车键重新解压. . .多次失败请手动下载更新")
                return False
        else:
            mediator.download_complete.emit(file_name)

    except requests.exceptions.RequestException as e:
        log.error(f"下载失败，请检查网络: {e}")
    except OSError as e:
        log.error(f"文件操作失败: {e}")
    finally:
        response.close()  # 确保关闭响应对象


def start_update_thread(assets_url):
    """
    在单独的线程中启动更新功能。
    :param assets_url: 更新文件的URL。
    """
    thread = Thread(target=update, args=(assets_url,))
    thread.start()
    return thread


def start_update(assert_name):
    source_file = os.path.abspath("./AALC Updater.exe")
    subprocess.Popen([source_file, assert_name], creationflags=subprocess.DETACHED_PROCESS)
