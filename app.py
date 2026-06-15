from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

app = Flask(__name__)

DEFAULT_TIMEOUT = 10
MIN_TIMEOUT = 1
MAX_TIMEOUT = 30

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def is_valid_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def parse_timeout(timeout_param: str) -> float:
    try:
        timeout = float(timeout_param)
    except (ValueError, TypeError):
        return DEFAULT_TIMEOUT
    return max(MIN_TIMEOUT, min(timeout, MAX_TIMEOUT))


def extract_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        return soup.title.string.strip()

    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return og_title["content"].strip()

    twitter_title = soup.find("meta", attrs={"name": "twitter:title"})
    if twitter_title and twitter_title.get("content"):
        return twitter_title["content"].strip()

    h1 = soup.find("h1")
    if h1 and h1.get_text():
        return h1.get_text().strip()

    return ""


@app.route("/get-title", methods=["GET"])
def get_title():
    url = request.args.get("url")
    timeout_param = request.args.get("timeout")

    if not url:
        return jsonify({"success": False, "error": "Missing 'url' parameter"}), 400

    if not is_valid_url(url):
        return jsonify({"success": False, "error": "Invalid URL format"}), 400

    timeout = parse_timeout(timeout_param)

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=timeout,
            allow_redirects=True
        )
        response.raise_for_status()

        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding

        title = extract_title(response.text)

        if not title:
            return jsonify({"success": False, "error": "No title found on the page"}), 404

        return jsonify({
            "success": True,
            "url": url,
            "title": title,
            "status_code": response.status_code,
            "timeout_used": timeout
        })

    except requests.exceptions.Timeout:
        return jsonify({"success": False, "error": "Request timed out", "timeout_used": timeout}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({"success": False, "error": "Connection error"}), 502
    except requests.exceptions.HTTPError as e:
        return jsonify({"success": False, "error": f"HTTP error: {e.response.status_code}"}), e.response.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({"success": False, "error": f"Request failed: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": f"Internal error: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
