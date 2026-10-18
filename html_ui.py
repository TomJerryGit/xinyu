# -*- coding: utf-8 -*-
"""HTML 入口：把模板、CSS、JS 拼接成一个完整的 HTML 字符串。

pywebview 直接渲染该字符串，避免 file:// 资源加载与跨域限制。
打包后模板位于 PyInstaller 的临时资源目录，因此统一走 ``resource_path``。
"""
from utils import resource_path


def _read(relative_path):
    with open(resource_path(relative_path), "r", encoding="utf-8") as handle:
        return handle.read()


def build_html(web_mode=False, token=""):
    """读取模板和静态文件，返回完整 HTML；缺文件时返回可读的错误页。"""
    try:
        html = _read("templates/index.html")
        css = _read("static/css/style.css")
        js = _read("static/js/main.js")
        html = html.replace("<!-- INLINE_CSS -->", f"<style>\n{css}\n</style>")
        if web_mode:
            shim = _read("static/js/web_shim.js")
            prefix = f'<script>window.__XINYU_TOKEN__="{token}";</script>\n' if token else ""
            html = html.replace(
                "<!-- INLINE_JS -->",
                f"{prefix}<script>\n{shim}\n</script>\n<script>\n{js}\n</script>",
            )
        else:
            html = html.replace("<!-- INLINE_JS -->", f"<script>\n{js}\n</script>")
        return html
    except Exception as exc:  # noqa: BLE001
        return (
            "<html><head><meta charset='utf-8'><title>心语启动失败</title></head>"
            "<body style='font-family:sans-serif;padding:40px'>"
            "<h2>界面资源加载失败</h2>"
            f"<p>{exc}</p>"
            "<p>请确认 templates/index.html、static/css/style.css、static/js/main.js 存在。</p>"
            "</body></html>"
        )


HTML = build_html()
