"""
Module for managing the download of Selenium webdriver binaries.

This code is released under the MIT license.
"""
import abc
import os
import os.path
from pathlib import Path
import platform
import shutil
import tarfile
from urllib.parse import urlparse, urlsplit
import zipfile
from bs4 import BeautifulSoup
import requests
import tqdm
from .util import get_architecture_bitness
from loguru import logger

logger.disable("webdriverdownloader2")


class WebDriverDownloaderBase:
    """Abstract Base Class for the different web driver downloaders"""

    __metaclass__ = abc.ABCMeta

    def __init__(self, download_root=None, link_path=None, os_name=None):
        """
        Initializer for the class.  Accepts three optional parameters.

        :param download_root: Path where the web driver binaries will be downloaded.  If running as root in macOS or
                              Linux, the default will be '/usr/local/webdriver', otherwise will be '$HOME/webdriver'.
        :param link_path: Path where the link to the web driver binaries will be created.  If running as root in macOS
                          or Linux, the default will be 'usr/local/bin', otherwise will be '$HOME/bin'.  On macOS and
                          Linux, a symlink will be created.
        :param os_name: Name of the OS to download the web driver binary for, as a str.  If not specified, we will use
                        platform.system() to get the OS.
        """
        self.os_name = platform.system() if os_name is None else os_name

        base_path = Path("/usr/local") if self.os_name in ["Darwin", "Linux"] and (os.geteuid() == 0) else Path.home()

        self.download_root = base_path.joinpath("webdriver") if download_root is None else download_root

        self.link_path = base_path.joinpath("bin") if link_path is None else link_path

        self.download_root.mkdir(parents=True, exist_ok=True)
        logger.info(f"Download root directory: {str(self.download_root)}")
        self.link_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Symlink directory: {str(self.link_path)}")

    @abc.abstractmethod
    def get_driver_filename(self, os_name=None):
        """
        Method for getting the filename of the web driver binary.

        :param os_name: Name of the OS to download the web driver binary for, as a str.  If not specified, we will use
                        platform.system() to get the OS.
        :returns: The filename of the web driver binary.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def get_download_path(self, version="latest"):
        """
        Method for getting the target download path for a web driver binary.

        :param version: String representing the version of the web driver binary to download.  For example, "2.38".
                        Default if no version is specified is "latest".  The version string should match the version
                        as specified on the download page of the webdriver binary.

        :returns: The target download path of the web driver binary.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def get_download_url(self, version="latest", os_name=None, bitness=None):
        """
        Method for getting the source download URL for a web driver binary.

        :param version: String representing the version of the web driver binary to download.  For example, "2.38".
                        Default if no version is specified is "latest".  The version string should match the version
                        as specified on the download page of the webdriver binary.
        :param os_name: Name of the OS to download the web driver binary for, as a str.  If not specified, we will use
                        platform.system() to get the OS.
        :param bitness: Bitness of the web driver binary to download, as a str e.g. "32", "64".  If not specified, we
                        will try to guess the bitness by using util.get_architecture_bitness().
        :returns: The source download URL for the web driver binary.
        """
        raise NotImplementedError

    def download(
        self, version="latest", os_name=None, bitness=None, show_progress_bar=True
    ):
        """
        Method for downloading a web driver binary.

        :param version: String representing the version of the web driver binary to download.  For example, "2.38".
                        Default if no version is specified is "latest".  The version string should match the version
                        as specified on the download page of the webdriver binary.  Prior to downloading, the method
                        will check the local filesystem to see if the driver has been downloaded already and will
                        skip downloading if the file is already present locally.
        :param os_name: Name of the OS to download the web driver binary for, as a str.  If not specified, we will use
                        platform.system() to get the OS.
        :param bitness: Bitness of the web driver binary to download, as a str e.g. "32", "64".  If not specified, we
                        will try to guess the bitness by using util.get_architecture_bitness().
        :param show_progress_bar: Boolean (default=True) indicating if a progress bar should be shown in the console.
        :returns: The path + filename to the downloaded web driver binary.
        """
        download_url = self.get_download_url(version, bitness=bitness)
        filename = (
            os.path.split(urlparse(download_url).path)[1].split("%2F")[1]
            if not "mozilla" in download_url
            else os.path.split(urlparse(download_url).path)[1]
        )
        self.download_path = self.get_download_path(version)
        filename_with_path = self.download_path.joinpath(filename)
        self.download_path.mkdir(parents=True, exist_ok=True)
        if filename_with_path.exists():
            logger.info(
                f"Skipping download. File {str(filename_with_path)} already on filesystem."
            )
            return filename_with_path
        else:
            data = requests.get(download_url, stream=True)
            if data.status_code == 200:
                logger.debug(
                    f"Starting download of {download_url} to {str(filename_with_path)}"
                )
                with open(filename_with_path, mode="wb") as fileobj:
                    chunk_size = 1024
                    if show_progress_bar:
                        expected_size = int(data.headers["Content-Length"])
                        for chunk in tqdm.tqdm(
                            data.iter_content(chunk_size),
                            total=int(expected_size / chunk_size),
                            unit="kb",
                        ):
                            fileobj.write(chunk)
                    else:
                        for chunk in data.iter_content(chunk_size):
                            fileobj.write(chunk)
                logger.debug(
                    f"Finished downloading {download_url} to {str(filename_with_path)}"
                )
                return filename_with_path
            else:
                error_message = (
                    f"Error downloading file {filename}, got status code: {data.status_code}"
                )
                logger.error(error_message)
                raise RuntimeError(error_message)

    def extract_file(self, filename_with_path):
        filename = filename_with_path.stem
        extract_dir = self.download_path.joinpath(filename)
        if extract_dir.exists():
            return extract_dir
        else:
            extract_dir.mkdir(parents=True)
            logger.debug(f"Created directory: {str(extract_dir)}")
        if ".zip" in filename_with_path.suffixes:
            with zipfile.ZipFile(filename_with_path, mode="r") as zip_file:
                zip_file.extractall(extract_dir)
            return extract_dir
        elif ".tar" in filename_with_path.suffixes:
            with tarfile.open(filename_with_path, mode="r:*") as tar_file:
                tar_file.extractall(extract_dir)
            return extract_dir
        else:
            error_message = f"Unknown archive format: {filename}"
            logger.error(error_message)
            raise RuntimeError(error_message)

    def download_and_install(
        self,
        version="latest",
        os_name=None,
        bitness=None,
        show_progress_bar=True,
    ):
        """
        Method for downloading a web driver binary, extracting it into the download directory and creating a symlink
        to the binary in the link directory.

        :param version: String representing the version of the web driver binary to download.  For example, "2.38".
                        Default if no version is specified is "latest".  The version string should match the version
                        as specified on the download page of the webdriver binary.
        :param os_name: Name of the OS to download the web driver binary for, as a str.  If not specified, we will use
                        platform.system() to get the OS.
        :param bitness: Bitness of the web driver binary to download, as a str e.g. "32", "64".  If not specified, we
                        will try to guess the bitness by using util.get_architecture_bitness().
        :param show_progress_bar: Boolean (default=True) indicating if a progress bar should be shown in the console.
        :returns: Tuple containing the path + filename to [0] the extracted binary, and [1] the symlink to the
                  extracted binary.
        """
        filename_with_path = self.download(
            version,
            os_name=os_name,
            bitness=bitness,
            show_progress_bar=show_progress_bar,
        )
        extract_dir_path = self.extract_file(filename_with_path)

        driver_filename = self.get_driver_filename(os_name=os_name)

        os_name = self.os_name if os_name is None else os_name

        if os_name in ["Darwin", "Linux"]:
            symlink_src_path = [el for el in extract_dir_path.iterdir() if el.is_file() and (el.name == driver_filename)][-1]

            symlink_target_path = Path(self.link_path).joinpath(driver_filename)

            if not symlink_target_path.exists():
                logger.warning(f"{symlink_target_path.name} Does not exist")
            if not symlink_src_path.exists():
                logger.warning(f"{str(symlink_src_path)} Does not exist")

            if symlink_target_path.is_symlink():
                same_file_link = symlink_src_path.samefile(symlink_target_path)
                if same_file_link:
                    logger.info(
                            f"Symlink already exists: {str(symlink_target_path)} -> {str(symlink_src_path)}"
                        )
                    symlink_src_path.chmod(0o755)
                    symlink_target_path.chmod(0o755)
                    return tuple([str(symlink_src_path), str(symlink_target_path)])
            else:
                symlink_target_path.symlink_to(symlink_src_path)
                logger.info(f"Created symlink: {str(symlink_target_path)} -> {str(symlink_src_path)}")
                symlink_src_path.chmod(0o755)
                symlink_target_path.chmod(0o755)
                return tuple([str(symlink_src_path), str(symlink_target_path)])
        elif os_name == "Windows":
            src_file = [
                entry.path
                for entry in os.scandir(extract_dir_path)
                if entry.is_file() and (entry.name == driver_filename)
            ][-1]
            dest_file = os.path.join(self.link_path, driver_filename)
            if os.path.isfile(dest_file):
                logger.info(
                    f"File {dest_file} already exists and will be overwritten."
                )
            shutil.copy2(src_file, dest_file)
            return tuple([src_file, dest_file])


class GeckoDriverDownloader(WebDriverDownloaderBase):
    """Class for downloading the Gecko (Mozilla Firefox) WebDriver."""

    gecko_driver_releases_api_url = (
        "https://api.github.com/repos/mozilla/geckodriver/releases/"
    )
    gecko_driver_releases_ui_url = "https://github.com/mozilla/geckodriver/releases/"

    def get_driver_filename(self, os_name=None):
        """
        Method for getting the filename of the web driver binary.

        :param os_name: Name of the OS to download the web driver binary for, as a str.  If not specified, we will use
                        platform.system() to get the OS.
        :returns: The filename of the web driver binary.
        """
        os_name = self.os_name if not os_name else os_name
        return "geckodriver" if os_name != "Windows" else "geckodriver.exe"

    def get_download_path(self, version="latest"):
        if version == "latest":
            info = requests.get(self.gecko_driver_releases_api_url + version)
            if info.status_code == 200:
                ver = info.json()["tag_name"]
                return os.path.join(self.download_root, "gecko", ver)
            else:
                info_message = f"Error attempting to get version info via API, got status code: {info.status_code}"
                logger.info(info_message)
                resp = requests.get(self.gecko_driver_releases_ui_url + version)
                if resp.status_code == 200:
                    ver = Path(urlsplit(resp.url).path).name
                    return os.path.join(self.download_root, "gecko", ver)
                else:
                    logger.error(
                        f"Got response code: {resp.status_code} with content: {resp.content}"
                    )
        else:
            return os.path.join(self.download_root, "gecko", version)

    def get_download_url(self, version="latest", os_name=None, bitness=None):
        """
        Method for getting the download URL for the Gecko (Mozilla Firefox) driver binary.

        :param version: String representing the version of the web driver binary to download.  For example, "v0.20.1".
                        Default if no version is specified is "latest".  The version string should match the version
                        as specified on the download page of the webdriver binary.
        :param os_name: Name of the OS to download the web driver binary for, as a str.  If not specified, we will use
                        platform.system() to get the OS.
        :param bitness: Bitness of the web driver binary to download, as a str e.g. "32", "64".  If not specified, we
                        will try to guess the bitness by using util.get_architecture_bitness().
        :returns: The download URL for the Gecko (Mozilla Firefox) driver binary.
        """
        gecko_driver_version_release_api_url = (
            self.gecko_driver_releases_api_url + version
            if version == "latest"
            else self.gecko_driver_releases_api_url + "tags/" + version
        )
        gecko_driver_version_release_ui_url = (
            self.gecko_driver_releases_ui_url + version
            if version == "latest"
            else self.gecko_driver_releases_ui_url + "tags/" + version
        )

        os_map = {"Darwin": "mac", "Windows": "win", "Linux": "linux"}
        os_name = os_map[self.os_name] if os_name is None else os_name

        if bitness is None:
            bitness = get_architecture_bitness()
            logger.debug(f"Detected OS: {bitness}bit {os_name}")


        logger.debug(
            f"Attempting to access URL: {gecko_driver_version_release_api_url}"
        )
        info = requests.get(gecko_driver_version_release_api_url)
        if info.status_code == 200:
            json_data = info.json()
        else:
            json_data = {"assets": []}
            logger.info(
                f"Error, unable to get info for gecko driver {version} release. Status code: {info.status_code}"
            )
            resp = requests.get(
                gecko_driver_version_release_ui_url, allow_redirects=True
            )
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, features="html.parser")
                urls = [
                    resp.url + a["href"]
                    for a in soup.find_all("a", href=True)
                    if r"/download/" in a["href"]
                ]
                for url in urls:
                    json_data["assets"].append(
                        {"name": Path(urlsplit(url).path).name, "browser_download_url": url}
                    )

        filenames = [asset["name"] for asset in json_data["assets"] if len(json_data["assets"]) > 0]
        filename = [name for name in filenames if (os_name in name) and (len(filenames) > 0)]
        if len(filename) == 0:
            info_message = f"Error, unable to find a download for os: {os_name}"
            logger.error(info_message)
            raise RuntimeError(info_message)
        if len(filename) > 1:
            filename = [name for name in filenames if os_name + bitness in name]
            if len(filename) != 1:
                info_message = (
                    f"Error, unable to determine correct filename for {bitness}bit {os_name}"
                )
                logger.error(info_message)
                raise RuntimeError(info_message)
        filename = filename[0]

        result = json_data["assets"][filenames.index(filename)]["browser_download_url"]
        logger.info(f"Download URL: {result}")
        return result


class ChromeDriverDownloader(WebDriverDownloaderBase):
    """Class for downloading the Google Chrome WebDriver."""

    chrome_driver_base_url = "https://www.googleapis.com/storage/v1/b/chromedriver"

    def _get_latest_version_number(self):
        resp = requests.get(self.chrome_driver_base_url + "/o/LATEST_RELEASE")
        if resp.status_code != 200:
            error_message = f"Error, unable to get version number for latest release, got code: {resp.status_code}"
            logger.error(error_message)
            raise RuntimeError(error_message)
        latest_release = requests.get(resp.json()["mediaLink"])
        return latest_release.text

    def get_driver_filename(self, os_name=None):
        """
        Method for getting the filename of the web driver binary.

        :param os_name: Name of the OS to download the web driver binary for, as a str.  If not specified, we will use
                        platform.system() to get the OS.
        :returns: The filename of the web driver binary.
        """

        os_name = self.os_name if not os_name else os_name
        return "chromedriver" if os_name != "Windows" else "chromedriver.exe"

    def get_download_path(self, version="latest"):
        if version == "latest":
            ver = self._get_latest_version_number()
        else:
            ver = version

        return Path(self.download_root).joinpath("chrome", ver)

    def get_download_url(self, version="latest", os_name=None, bitness=None):
        """
        Method for getting the download URL for the Google Chome driver binary.

        :param version: String representing the version of the web driver binary to download.  For example, "2.39".
                        Default if no version is specified is "latest".  The version string should match the version
                        as specified on the download page of the webdriver binary.
        :param os_name: Name of the OS to download the web driver binary for, as a str.  If not specified, we will use
                        platform.system() to get the OS.
        :param bitness: Bitness of the web driver binary to download, as a str e.g. "32", "64".  If not specified, we
                        will try to guess the bitness by using util.get_architecture_bitness().
        :returns: The download URL for the Google Chrome driver binary.
        """
        if version == "latest":
            version = self._get_latest_version_number()

        os_map = {"Darwin": "mac", "Windows": "win", "Linux": "linux"}
        os_name = os_map[self.os_name] if os_name is None else os_name

        if bitness is None:
            bitness = get_architecture_bitness()
            logger.debug(f"Detected OS: {bitness}bit {os_name}")

        chrome_driver_objects = requests.get(self.chrome_driver_base_url + "/o")
        matching_versions = [
            item
            for item in chrome_driver_objects.json()["items"]
            if item["name"].startswith(version)
        ]
        os_matching_versions = [
            item for item in matching_versions if os_name in item["name"]
        ]
        if not os_matching_versions:
            error_message = (
                f"Error, unable to find appropriate download for {os_name + bitness}."
            )
            logger.error(error_message)
            raise RuntimeError(error_message)
        elif len(os_matching_versions) == 1:
            return os_matching_versions[0]["mediaLink"]
        elif len(os_matching_versions) == 2:
            return [
                item for item in matching_versions if os_name + bitness in item["name"]
            ][0]["mediaLink"]
