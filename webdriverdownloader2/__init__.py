try:
    from webdriverdownloader2 import (
        ChromeDriverDownloader,
        GeckoDriverDownloader,
    )
except ImportError:
    from .webdriverdownloader2 import (
        ChromeDriverDownloader,
        GeckoDriverDownloader,
    )

__all__ = [
    "ChromeDriverDownloader",
    "GeckoDriverDownloader",
]
