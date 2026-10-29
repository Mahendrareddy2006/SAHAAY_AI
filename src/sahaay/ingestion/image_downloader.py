"""
Sahaay AI - Safe Remote Image Downloader & Metadata Extractor
Provides SSRF-protected, bounded image retrieval and Open Graph image extraction.
"""

from io import BytesIO
import ipaddress
import logging
import re
import socket
from typing import List, Optional, Set
import urllib.parse
import urllib.request
from PIL import Image

logger = logging.getLogger(__name__)

# Maximum download size: 8 MB
MAX_IMAGE_BYTES = 8 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 6.0

# Prevent decompression bomb DOS attacks
Image.MAX_IMAGE_PIXELS = 10_000_000

# File extensions accepted
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Known tracking/icon keywords to ignore
IGNORED_IMAGE_PATTERNS = [
    r"favicon",
    r"logo",
    r"avatar",
    r"tracker",
    r"pixel",
    r"1x1",
    r"ad-",
    r"banner-ads",
    r"button",
]


def is_safe_public_url(url: str) -> bool:
    """
    Validates that a URL is a valid HTTP/HTTPS URL and does NOT resolve to a
    loopback, private, link-local, multicast, or cloud-metadata IP address (SSRF Protection).
    """
    if not url or not isinstance(url, str):
        return False

    try:
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme.lower() not in ("http", "https"):
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        # Reject plain localhost
        if hostname.lower() in ("localhost", "127.0.0.1", "::1"):
            return False

        # Resolve IP addresses for hostname
        addr_info = socket.getaddrinfo(hostname, None)
        if not addr_info:
            return False

        for family, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)

            # Block private, loopback, link-local, multicast, reserved
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                logger.warning(f"Blocked SSRF attempt to non-public IP: {ip_str} for URL {url}")
                return False

            # Specific check for AWS/GCP/Azure link-local metadata (169.254.169.254)
            if str(ip) == "169.254.169.254":
                logger.warning(f"Blocked SSRF attempt to metadata service: {ip_str}")
                return False

        return True
    except Exception as e:
        logger.debug(f"SSRF URL validation rejected '{url}': {e}")
        return False


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """
    HTTP redirect handler that validates target redirection URLs against SSRF policies.
    Blocks redirects to internal IP ranges, loopback, or metadata services.
    """
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not is_safe_public_url(newurl):
            logger.warning(f"Blocked SSRF redirect attempt to non-public URL: {newurl}")
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _build_safe_opener() -> urllib.request.OpenerDirector:
    """Builds an OpenerDirector equipped with SafeRedirectHandler."""
    return urllib.request.build_opener(SafeRedirectHandler)


def fetch_safe_article_html(
    url: str,
    max_bytes: int = 256 * 1024,
    timeout_seconds: float = 5.0,
) -> Optional[str]:
    """
    Safely retrieves article HTML for Open Graph and metadata inspection.
    Enforces SSRF boundary, bounded size (default 256KB), and safe redirects.
    """
    if not is_safe_public_url(url):
        logger.warning(f"Rejecting unsafe or private article URL: {url}")
        return None

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "SahaayAI-Hyderabad-Flood-Intel/1.0 (+https://github.com/Mahendrareddy2006/SAHAAY_AI)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        opener = _build_safe_opener()
        with opener.open(req, timeout=timeout_seconds) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type and "xml" not in content_type:
                logger.debug(f"Skipping non-HTML content type '{content_type}' from {url}")
                return None

            data = resp.read(max_bytes + 1)
            if len(data) > max_bytes:
                data = data[:max_bytes]

            return data.decode("utf-8", errors="ignore")
    except Exception as e:
        logger.debug(f"Failed to fetch article HTML from '{url}': {e}")
        return None


def fetch_remote_image(
    url: str,
    max_bytes: int = MAX_IMAGE_BYTES,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> Optional[bytes]:
    """
    Safely retrieves remote image bytes with SSRF check, strict size bounding, and format validation.
    Returns bytes if valid image, None otherwise.
    """
    if not is_safe_public_url(url):
        logger.warning(f"Rejecting unsafe or private image URL: {url}")
        return None

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "SahaayAI-Hyderabad-Flood-Intel/1.0 (+https://github.com/Mahendrareddy2006/SAHAAY_AI)",
                "Accept": "image/jpeg,image/png,image/webp,image/*",
            },
        )
        opener = _build_safe_opener()
        with opener.open(req, timeout=timeout_seconds) as resp:
            # Check content length header if provided
            content_length = resp.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                logger.warning(f"Remote image exceeds max size {max_bytes} bytes: {url}")
                return None

            data = resp.read(max_bytes + 1)
            if len(data) > max_bytes:
                logger.warning(f"Downloaded image exceeded max size limit {max_bytes}: {url}")
                return None

            # Verify image format and integrity with Pillow
            with Image.open(BytesIO(data)) as img:
                img.verify()
                format_name = (img.format or "").upper()
                if format_name not in ("JPEG", "PNG", "WEBP", "MPO"):
                    logger.warning(f"Unsupported image format '{format_name}' from {url}")
                    return None

            return data
    except Exception as e:
        logger.debug(f"Failed to fetch remote image from '{url}': {e}")
        return None


def extract_image_urls_from_article_html(html_text: str, base_url: str) -> List[str]:
    """
    Extracts high-confidence article image URLs (Open Graph, Twitter Card, article body)
    from article HTML content, filtering out tracking pixels and icons.
    """
    if not html_text:
        return []

    discovered: List[str] = []
    seen: Set[str] = set()

    # 1. Open Graph image tags: <meta property="og:image" content="...">
    og_matches = re.findall(
        r'<meta\s+[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']',
        html_text,
        re.IGNORECASE,
    )
    # Also check inverted content="..." property="og:image"
    og_matches += re.findall(
        r'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']',
        html_text,
        re.IGNORECASE,
    )

    # 2. Twitter Card image tags: <meta name="twitter:image" content="...">
    tw_matches = re.findall(
        r'<meta\s+[^>]*name=["\']twitter:image["\'][^>]*content=["\']([^"\']+)["\']',
        html_text,
        re.IGNORECASE,
    )
    tw_matches += re.findall(
        r'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*name=["\']twitter:image["\']',
        html_text,
        re.IGNORECASE,
    )

    # 3. Article body image tags (e.g. <article>...<img src="..."> or <figure>...<img src="...">)
    body_img_matches = re.findall(
        r'<figure[^>]*>\s*<img\s+[^>]*src=["\']([^"\']+)["\']',
        html_text,
        re.IGNORECASE,
    )

    candidates = og_matches + tw_matches + body_img_matches

    for raw_url in candidates:
        raw_url = raw_url.strip()
        if not raw_url:
            continue

        resolved_url = urllib.parse.urljoin(base_url, raw_url)
        if resolved_url in seen:
            continue
        seen.add(resolved_url)

        # Check ignored patterns
        lowered = resolved_url.lower()
        if any(re.search(pat, lowered) for pat in IGNORED_IMAGE_PATTERNS):
            continue

        if is_safe_public_url(resolved_url):
            discovered.append(resolved_url)

    return discovered
