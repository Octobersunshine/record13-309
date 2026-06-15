from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

DEFAULT_TIMEOUT = 10
MIN_TIMEOUT = 1
MAX_TIMEOUT = 30
MAX_BATCH_SIZE = 10

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


def fetch_title(url: str, timeout: float) -> dict:
    result = {"url": url, "success": False, "error": ""}

    if not is_valid_url(url):
        result["error"] = "Invalid URL format"
        return result

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
            result["error"] = "No title found on the page"
            return result

        result["success"] = True
        result["title"] = title
        result["status_code"] = response.status_code

    except requests.exceptions.Timeout:
        result["error"] = "Request timed out"
    except requests.exceptions.ConnectionError:
        result["error"] = "Connection error"
    except requests.exceptions.HTTPError as e:
        result["error"] = f"HTTP error: {e.response.status_code}"
    except requests.exceptions.RequestException as e:
        result["error"] = f"Request failed: {str(e)}"
    except Exception as e:
        result["error"] = f"Internal error: {str(e)}"

    return result


@app.route("/get-title", methods=["GET"])
def get_title():
    url = request.args.get("url")
    timeout_param = request.args.get("timeout")

    if not url:
        return jsonify({"success": False, "error": "Missing 'url' parameter"}), 400

    timeout = parse_timeout(timeout_param)
    result = fetch_title(url, timeout)
    result["timeout_used"] = timeout

    if result["success"]:
        return jsonify(result)
    else:
        status = 404 if "No title" in result["error"] else 502
        if "timed out" in result["error"]:
            status = 504
        return jsonify(result), status


@app.route("/batch-get-title", methods=["POST"])
def batch_get_title():
    data = request.get_json(silent=True)

    if not data or "urls" not in data:
        return jsonify({"success": False, "error": "Missing 'urls' field in JSON body"}), 400

    urls = data["urls"]

    if not isinstance(urls, list):
        return jsonify({"success": False, "error": "'urls' must be an array"}), 400

    if len(urls) == 0:
        return jsonify({"success": False, "error": "'urls' array is empty"}), 400

    if len(urls) > MAX_BATCH_SIZE:
        return jsonify({"success": False, "error": f"Maximum {MAX_BATCH_SIZE} URLs allowed, got {len(urls)}"}), 400

    timeout_param = data.get("timeout")
    timeout = parse_timeout(timeout_param)

    results = [None] * len(urls)

    with ThreadPoolExecutor(max_workers=min(len(urls), MAX_BATCH_SIZE)) as executor:
        future_to_index = {
            executor.submit(fetch_title, url, timeout): i
            for i, url in enumerate(urls)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            results[index] = future.result()

    success_count = sum(1 for r in results if r["success"])

    return jsonify({
        "success": True,
        "total": len(urls),
        "success_count": success_count,
        "fail_count": len(urls) - success_count,
        "timeout_used": timeout,
        "results": results
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
