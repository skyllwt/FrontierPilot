#!/usr/bin/env python3
"""
小红书重新登录脚本（xiaohongshu-mcp）

Cookie 到期或需要重新绑定账号时运行：
  python3 xhs_login.py

会在 /tmp/xhs_qrcode.png 生成二维码图片，用手机小红书 App 扫码，
完成后自动验证登录状态。
"""

import urllib.request
import json
import re
import base64
import subprocess
import sys
import os
import time

MCP_HOST = os.environ.get("XHS_MCP_HOST", "localhost")
MCP_PORT = os.environ.get("XHS_MCP_PORT", "18060")
MCP_URL = "http://{}:{}/mcp".format(MCP_HOST, MCP_PORT)
QR_PATH = "/tmp/xhs_qrcode.png"


def post_raw(body, session_id=None):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    req = urllib.request.Request(
        MCP_URL, data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            session = r.headers.get("Mcp-Session-Id", "")
            raw = r.read().decode(errors="replace")
            return raw, session
    except urllib.error.HTTPError as e:
        return e.read().decode(errors="replace"), ""


def mcp_session():
    """Initialize MCP session, return session_id."""
    raw, session = post_raw({
        "jsonrpc": "2.0", "id": 0, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "xhs-login", "version": "1.0"},
        },
    })
    # Send initialized notification
    post_raw({"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id=session)
    return session


def mcp_call(session_id, tool, arguments=None):
    """Call a xiaohongshu-mcp tool, return result text."""
    raw, _ = post_raw({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": tool, "arguments": arguments or {}},
    }, session_id=session_id)

    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            line = line[5:].strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except Exception:
                pass
    try:
        return json.loads(raw)
    except Exception:
        return {"_raw": raw}


def check_mcp_running():
    """Verify xiaohongshu-mcp container is accessible."""
    try:
        raw, _ = post_raw({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                           "params": {"protocolVersion": "2024-11-05",
                                      "capabilities": {},
                                      "clientInfo": {"name": "check", "version": "1"}}})
        return True
    except Exception as e:
        print("❌ 无法连接 xiaohongshu-mcp（{}:{}）: {}".format(MCP_HOST, MCP_PORT, e))
        print("   请先启动: docker start xiaohongshu-mcp")
        return False


def get_qrcode():
    """Fetch QR code as PNG and save to QR_PATH."""
    session = mcp_session()
    resp = mcp_call(session, "get_login_qrcode")
    text = json.dumps(resp)
    b64s = re.findall(r"[A-Za-z0-9+/]{100,}={0,2}", text)
    if not b64s:
        print("❌ 未能获取二维码（响应：{}）".format(text[:200]))
        return None
    img = base64.b64decode(b64s[0] + "==")
    with open(QR_PATH, "wb") as f:
        f.write(img)
    return QR_PATH


def check_login():
    """Return True if logged in."""
    session = mcp_session()
    resp = mcp_call(session, "check_login_status")
    text = json.dumps(resp, ensure_ascii=False)
    return "已登录" in text or "logged_in" in text.lower()


def main():
    print("小红书重新登录工具")
    print("=" * 40)

    if not check_mcp_running():
        sys.exit(1)

    if check_login():
        print("✅ 当前已登录，无需重新扫码。")
        return

    print("正在获取登录二维码...")
    path = get_qrcode()
    if not path:
        sys.exit(1)

    print("二维码已保存到 {}".format(path))

    # Try to open the image
    for cmd in ["xdg-open", "open", "eog", "display"]:
        if subprocess.run(["which", cmd], capture_output=True).returncode == 0:
            subprocess.Popen([cmd, path])
            break

    print("\n👉 用手机小红书 App 扫码（有效期约 2 分钟）")
    print("   扫码后等待自动验证...\n")

    for i in range(24):  # 等最多 2 分钟
        time.sleep(5)
        if check_login():
            print("✅ 登录成功！Cookie 已保存，约 1-3 个月有效。")
            return
        print("  等待扫码... ({}/24)".format(i + 1))

    print("❌ 超时未检测到登录，请重新运行此脚本。")
    sys.exit(1)


if __name__ == "__main__":
    main()
