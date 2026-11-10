#!/usr/bin/env python3
"""Bing Webmaster Tools MCP（零依赖 stdio JSON-RPC）。

API Key 由词真语 Deploy 注入：
  - 进程环境 BING_WEBMASTER_API_KEY
  - 或 CIZHENYU_AUTH_DIR/bing.json 的 apiKey
禁止在代码或仓库中写入密钥。
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SERVER_NAME = "bing_webmaster"
SERVER_VERSION = "1.0.0"
API_BASE = "https://ssl.bing.com/webmaster/api.svc/json"


class BingError(RuntimeError):
    pass


def auth_dir() -> Path | None:
    for key in ("CIZHENYU_AUTH_DIR", "SEOGEO_AUTH_DIR"):
        raw = os.environ.get(key, "").strip()
        if raw:
            return Path(raw)
    return None


def api_key() -> str:
    env = os.environ.get("BING_WEBMASTER_API_KEY", "").strip()
    if env:
        return env
    base = auth_dir()
    if not base:
        raise BingError("未设置 BING_WEBMASTER_API_KEY / CIZHENYU_AUTH_DIR")
    path = base / "bing.json"
    if not path.is_file():
        raise BingError(f"找不到 Bing 凭据：{path}")
    conf = json.loads(path.read_text(encoding="utf-8-sig"))
    key = (conf.get("apiKey") or conf.get("api_key") or "").strip()
    if not key:
        raise BingError("bing.json 缺少 apiKey")
    return key


def _call(method: str, params: dict | None = None, http: str = "GET") -> dict:
    q = {"apikey": api_key()}
    url = f"{API_BASE}/{method}?{urllib.parse.urlencode(q)}"
    data = None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if http == "POST":
        data = json.dumps(params or {}).encode("utf-8")
    elif params:
        url += "&" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(url, data=data, method=http, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60, context=ssl.create_default_context()) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise BingError(f"HTTP {exc.code}: {detail}") from exc


def get_user_sites() -> dict:
    return _call("GetUserSites")


def get_rank_and_traffic(site_url: str) -> dict:
    return _call("GetRankAndTrafficStats", {"siteUrl": site_url})


def get_query_stats(site_url: str) -> dict:
    return _call("GetQueryStats", {"siteUrl": site_url})


def get_crawl_stats(site_url: str) -> dict:
    return _call("GetCrawlStats", {"siteUrl": site_url})


def get_url_info(site_url: str, url: str) -> dict:
    return _call("GetUrlInfo", {"siteUrl": site_url, "url": url})


def submit_url(site_url: str, url: str) -> dict:
    return _call("SubmitUrl", {"siteUrl": site_url, "url": url}, http="POST")


def submit_url_batch(site_url: str, urls: list[str]) -> dict:
    return _call(
        "SubmitUrlBatch",
        {"siteUrl": site_url, "urlList": urls[:500]},
        http="POST",
    )


def get_sitemaps(site_url: str) -> dict:
    return _call("GetFeeds", {"siteUrl": site_url})


TOOLS = {
    "bing_sites": {
        "fn": get_user_sites,
        "desc": "列出当前 API Key 可管理的 Bing Webmaster 站点。",
        "schema": {"type": "object", "properties": {}, "required": []},
    },
    "bing_rank_traffic": {
        "fn": get_rank_and_traffic,
        "desc": "站点排名与流量趋势统计。",
        "schema": {
            "type": "object",
            "properties": {"site_url": {"type": "string"}},
            "required": ["site_url"],
        },
    },
    "bing_query_stats": {
        "fn": get_query_stats,
        "desc": "站点搜索查询词表现。",
        "schema": {
            "type": "object",
            "properties": {"site_url": {"type": "string"}},
            "required": ["site_url"],
        },
    },
    "bing_crawl_stats": {
        "fn": get_crawl_stats,
        "desc": "站点抓取统计（爬虫命中/错误等）。",
        "schema": {
            "type": "object",
            "properties": {"site_url": {"type": "string"}},
            "required": ["site_url"],
        },
    },
    "bing_url_info": {
        "fn": get_url_info,
        "desc": "查询单个 URL 在 Bing 中的索引/抓取信息。",
        "schema": {
            "type": "object",
            "properties": {
                "site_url": {"type": "string"},
                "url": {"type": "string"},
            },
            "required": ["site_url", "url"],
        },
    },
    "bing_submit_url": {
        "fn": submit_url,
        "desc": "向 Bing 提交单个 URL（IndexNow/URL submission）。",
        "schema": {
            "type": "object",
            "properties": {
                "site_url": {"type": "string"},
                "url": {"type": "string"},
            },
            "required": ["site_url", "url"],
        },
    },
    "bing_submit_url_batch": {
        "fn": submit_url_batch,
        "desc": "批量提交 URL（最多 500）。",
        "schema": {
            "type": "object",
            "properties": {
                "site_url": {"type": "string"},
                "urls": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["site_url", "urls"],
        },
    },
    "bing_sitemaps": {
        "fn": get_sitemaps,
        "desc": "列出已提交的 sitemap / feed。",
        "schema": {
            "type": "object",
            "properties": {"site_url": {"type": "string"}},
            "required": ["site_url"],
        },
    },
}


def call_tool(name: str, args: dict) -> dict:
    spec = TOOLS.get(name)
    if not spec:
        return {"ok": False, "error": f"unknown tool: {name}"}
    try:
        return {"ok": True, "tool": name, "result": spec["fn"](**args)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "tool": name, "error": f"{type(exc).__name__}: {exc}"}


def _reply(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def serve() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        method, msg_id, params = msg.get("method"), msg.get("id"), (msg.get("params") or {})
        if method == "initialize":
            _reply(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": params.get("protocolVersion", "2025-06-18"),
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    },
                }
            )
        elif method in ("notifications/initialized", "initialized"):
            continue
        elif method == "tools/list":
            _reply(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "tools": [
                            {"name": n, "description": s["desc"], "inputSchema": s["schema"]}
                            for n, s in TOOLS.items()
                        ]
                    },
                }
            )
        elif method == "tools/call":
            result = call_tool(params.get("name", ""), params.get("arguments") or {})
            _reply(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]
                    },
                }
            )
        elif method == "ping":
            _reply({"jsonrpc": "2.0", "id": msg_id, "result": {}})
        elif msg_id is not None:
            _reply(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"method not found: {method}"},
                }
            )


if __name__ == "__main__":
    serve()
