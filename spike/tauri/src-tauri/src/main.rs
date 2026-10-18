// Tauri 2 spike: thin WebView2 window + Python sidecar.
// 本机没有 Rust/MSVC 工具链，尚未编译；代码按 Tauri 2 API 编写。
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpStream;
use std::os::windows::process::CommandExt;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

const CREATE_NO_WINDOW: u32 = 0x08000000;

struct Sidecar(Mutex<Option<Child>>);

fn sidecar_command(app: &tauri::App) -> Command {
    let mut roots: Vec<PathBuf> = Vec::new();
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            roots.push(parent.to_path_buf());
        }
    }
    if let Ok(resource_dir) = app.path().resource_dir() {
        roots.push(resource_dir);
    }
    if let Ok(root) = std::env::var("XINYU_ROOT") {
        roots.push(PathBuf::from(root));
    }
    roots.push(PathBuf::from(r"D:\xinyu"));

    // 首选嵌入式 Python：启动约 1.2s，比 PyInstaller 快。
    for root in &roots {
        let embedded = root.join("sidecar").join("embedded");
        let python = embedded.join("python").join("python.exe");
        let script = embedded.join("app").join("sidecar_server.py");
        if python.exists() && script.exists() {
            let mut command = Command::new(python);
            command.arg(script);
            command.creation_flags(CREATE_NO_WINDOW);
            return command;
        }
    }

    // 回退 PyInstaller onedir sidecar。
    let mut candidates: Vec<PathBuf> = Vec::new();
    for root in &roots {
        candidates.push(root.join("sidecar").join("XinyuSidecar").join("XinyuSidecar.exe"));
        candidates.push(root.join("dist").join("XinyuSidecar").join("XinyuSidecar.exe"));
    }
    candidates.push(PathBuf::from(r"D:\xinyu\dist\XinyuSidecar\XinyuSidecar.exe"));

    let mut command = if let Some(exe) = candidates.iter().find(|path| path.exists()) {
        Command::new(exe)
    } else {
        let root = std::env::var("XINYU_ROOT").unwrap_or_else(|_| r"D:\xinyu".to_string());
        let mut python = Command::new("python");
        python.arg(format!(r"{}\sidecar_server.py", root));
        python
    };
    command.creation_flags(CREATE_NO_WINDOW);
    command
}

fn wait_port(port: u16, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    false
}

fn main() {
    let app = tauri::Builder::default()
        .setup(|app| {
            let prestarted = TcpStream::connect(("127.0.0.1", 18765)).is_ok();
            let data_dir = app
                .path()
                .data_dir()
                .map(|path| path.join("Xinyu"))
                .unwrap_or_else(|_| PathBuf::from(r"D:\xinyu"));
            let child = if prestarted {
                None
            } else {
                Some(
                    sidecar_command(app)
                        .arg("--data-dir")
                        .arg(data_dir)
                        .args(["--port", "18765"])
                        .spawn()
                        .expect("启动 Python sidecar 失败"),
                )
            };
            app.manage(Sidecar(Mutex::new(child)));

            // 预启动时给 WebView2 一点初始化时间再导航；冷启动先显示 splash。
            let initial_url = WebviewUrl::App("index.html".into());
            let window = WebviewWindowBuilder::new(app, "main", initial_url)
                .title("心语 V9.3.0")
                .inner_size(1160.0, 780.0)
                .min_inner_size(900.0, 620.0)
                .build()?;

            let handle = window.clone();
            std::thread::spawn(move || {
                if prestarted {
                    std::thread::sleep(Duration::from_millis(1200));
                } else if !wait_port(18765, Duration::from_secs(20)) {
                    return;
                }
                let _ = handle.navigate("http://127.0.0.1:18765".parse().unwrap());
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("构建 Tauri 应用失败");

    app.run(|app_handle, event| {
        if let tauri::RunEvent::Exit = event {
            if let Some(state) = app_handle.try_state::<Sidecar>() {
                if let Ok(mut guard) = state.0.lock() {
                    if let Some(mut child) = guard.take() {
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                }
            }
        }
    });
}
