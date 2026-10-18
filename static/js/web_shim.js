/* Web/Tauri 运行时的 pywebview 兼容层。
 * 由 sidecar_server.py 注入 token，页面通过同源 /api/<method> 调用 Python。
 */
(function () {
    'use strict';
    const token = window.__XINYU_TOKEN__ || '';
    const api = new Proxy({}, {
        get(_target, name) {
            if (name === 'then') return undefined;
            return function (...args) {
                return fetch('/api/' + encodeURIComponent(String(name)), {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Xinyu-Token': token,
                    },
                    body: JSON.stringify({ args }),
                }).then(async (response) => {
                    if (!response.ok) {
                        throw new Error('sidecar HTTP ' + response.status);
                    }
                    return response.json();
                });
            };
        },
    });
    window.pywebview = { api };
    window.__XINYU_WEB__ = true;
    setTimeout(() => window.dispatchEvent(new Event('pywebviewready')), 0);
})();
