#!/user/bin/env python3
import logging
import lzma
import os
from pathlib import Path
import shutil
import threading
import zipfile
import concurrent.futures
import json

import requests

PATH_BASE = Path(__file__).parent.resolve()
PATH_BASE_MODULE: Path = PATH_BASE.joinpath("base")
PATH_BUILD: Path = PATH_BASE.joinpath("build")
PATH_BUILD_TMP: Path = PATH_BUILD.joinpath("tmp")
PATH_DOWNLOADS: Path = PATH_BASE.joinpath("downloads")

logger = logging.getLogger()
syslog = logging.StreamHandler()
formatter = logging.Formatter("%(threadName)s : %(message)s")
syslog.setFormatter(formatter)
logger.setLevel(logging.INFO)
logger.addHandler(syslog)


def download_file(url: str, path: Path):
    file_name = url[url.rfind("/") + 1:]
    logger.info(f"Downloading '{file_name}' to '{path}'")

    if path.exists():
        return

    r = requests.get(url, allow_redirects=True)
    with open(path, "wb") as f:
        f.write(r.content)

    logger.info("Done")


def extract_file(archive_path: Path, dest_path: Path):
    logger.info(f"Extracting '{archive_path.name}' to '{dest_path.name}'")

    with lzma.open(archive_path) as f:
        file_content = f.read()
        path = dest_path.parent

        path.mkdir(parents=True, exist_ok=True)

        with open(dest_path, "wb") as out:
            out.write(file_content)


def create_module_prop(path: Path, project_tag: str):
    module_prop = f"""id=magisk-hluda
name=MagiskHluda
version={project_tag}
versionCode={project_tag.replace(".", "").replace("-", "")}
author=StimeKe
description=Run hluda-server on boot
updateJson=https://github.com/StimeKe/magisk-hluda/releases/latest/download/updater.json"""

    with open(path.joinpath("module.prop"), "w", newline="\n") as f:
        f.write(module_prop)


def create_module(project_tag: str):
    logger.info("Creating module")

    if PATH_BUILD_TMP.exists():
        shutil.rmtree(PATH_BUILD_TMP)

    shutil.copytree(PATH_BASE_MODULE, PATH_BUILD_TMP)
    create_module_prop(PATH_BUILD_TMP, project_tag)


def fill_module(arch: str, hluda_tag: str, project_tag: str):
    threading.current_thread().setName(arch)
    logger.info(f"Filling module for arch '{arch}'")

    hluda_download_url = f"https://github.com/Ylarod/Florida/releases/download/{hluda_tag}/"
    hluda_server = f"hluda-server-{hluda_tag}-android-{arch}.xz"
    hluda_server_path = PATH_DOWNLOADS.joinpath(hluda_server)

    download_file(hluda_download_url + hluda_server, hluda_server_path)
    files_dir = PATH_BUILD_TMP.joinpath("files")
    files_dir.mkdir(exist_ok=True)
    extract_file(hluda_server_path, files_dir.joinpath(f"hluda-server-{arch}"))


def create_updater_json(project_tag: str):
    logger.info("Creating updater.json")
    
    updater ={
        "version": project_tag,
        "versionCode": int(project_tag.replace(".", "").replace("-", "")),
        "zipUrl": f"https://github.com/StimeKe/magisk-hluda/releases/download/{project_tag}/MagiskHluda-{project_tag}.zip",
        "changelog": "https://raw.githubusercontent.com/StimeKe/magisk-hluda/master/CHANGELOG.md"
    }

    with open(PATH_BUILD.joinpath("updater.json"), "w", newline="\n") as f:
        f.write(json.dumps(updater, indent = 4))

def package_module(project_tag: str):
    logger.info("Packaging module")

    module_zip = PATH_BUILD.joinpath(f"MagiskHluda-{project_tag}.zip")

    with zipfile.ZipFile(module_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(PATH_BUILD_TMP):
            for file_name in files:
                if file_name == "placeholder" or file_name == ".gitkeep":
                    continue
                zf.write(Path(root).joinpath(file_name),
                         arcname=Path(root).relative_to(PATH_BUILD_TMP).joinpath(file_name))

    shutil.rmtree(PATH_BUILD_TMP)


def do_build(hluda_tag: str, project_tag: str):
    PATH_DOWNLOADS.mkdir(parents=True, exist_ok=True)
    PATH_BUILD.mkdir(parents=True, exist_ok=True)

    create_module(project_tag)

    archs = ["arm", "arm64", "x86", "x86_64"]
    executor = concurrent.futures.ProcessPoolExecutor()
    futures = [executor.submit(fill_module, arch, hluda_tag, project_tag)
               for arch in archs]
    for future in concurrent.futures.as_completed(futures):
        if future.exception() is not None:
            raise future.exception()
    # TODO: Causes 'OSError: The handle is invalid' in Python 3.7, revert after update
    # executor.shutdown()

    package_module(project_tag)
    create_updater_json(project_tag)

    logger.info("Done")
