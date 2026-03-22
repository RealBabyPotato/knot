#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use std::env;
use std::net::{SocketAddr, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;
use tauri::{Manager, State, WindowUrl};

const DEFAULT_FRONTEND_URL: &str = "http://127.0.0.1:1420";
const DEFAULT_BACKEND_BINARY: &str = "python3";

#[derive(Clone, Debug)]
struct AppConfig {
    workspace_dir: PathBuf,
    frontend_url: FrontendTarget,
    backend: BackendCommand,
    backend_url: String,
}

#[derive(Clone, Debug)]
enum FrontendTarget {
    External(String),
    App(PathBuf),
}

#[derive(Clone, Debug)]
struct BackendCommand {
    binary: String,
    args: Vec<String>,
}

struct BackendProcess {
    child: Option<Child>,
    pid: Option<u32>,
}

struct AppState {
    config: AppConfig,
    backend: Mutex<BackendProcess>,
}

#[derive(Serialize)]
struct BackendStatus {
    running: bool,
    pid: Option<u32>,
    url: String,
    backend_command: String,
}

#[derive(Serialize)]
struct AppInfo {
    workspace_dir: String,
    frontend_url: String,
    backend_url: String,
}

#[tauri::command]
fn app_info(state: State<'_, AppState>) -> AppInfo {
    AppInfo {
        workspace_dir: state.config.workspace_dir.display().to_string(),
        frontend_url: frontend_url_string(&state.config.frontend_url),
        backend_url: state.config.backend_url.clone(),
    }
}

#[tauri::command]
fn backend_status(state: State<'_, AppState>) -> BackendStatus {
    let backend = state.backend.lock().expect("backend mutex poisoned");
    BackendStatus {
        running: backend.is_running() || port_is_open(&state.config.backend_url),
        pid: backend.pid,
        url: state.config.backend_url.clone(),
        backend_command: format_backend_command(&state.config.backend),
    }
}

#[tauri::command]
fn restart_backend(state: State<'_, AppState>) -> Result<BackendStatus, String> {
    {
        let mut backend = state.backend.lock().map_err(|_| "backend mutex poisoned")?;
        backend.stop();
    }

    start_backend(&state.config, &state.backend)?;
    let backend = state.backend.lock().map_err(|_| "backend mutex poisoned")?;
    Ok(backend_status_from(backend.pid, &state.config))
}

fn main() {
    let config = AppConfig::from_env();
    let state = AppState {
        config: config.clone(),
        backend: Mutex::new(BackendProcess::stopped()),
    };

    tauri::Builder::default()
        .manage(state)
        .invoke_handler(tauri::generate_handler![
            app_info,
            backend_status,
            restart_backend
        ])
        .setup(move |app| {
            if app.get_window("main").is_none() {
                let _window = tauri::WindowBuilder::new(
                    app,
                    "main",
                    match &config.frontend_url {
                        FrontendTarget::External(url) => {
                            WindowUrl::External(url.parse().expect("invalid frontend url"))
                        }
                        FrontendTarget::App(path) => WindowUrl::App(path.clone()),
                    },
                )
                .title("Knot")
                .inner_size(1280.0, 900.0)
                .resizable(true)
                .build()?;
            }

            let state = app.state::<AppState>();
            start_backend(&config, &state.backend)?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running knot desktop app");
}

impl AppConfig {
    fn from_env() -> Self {
        let workspace_dir = locate_workspace_dir()
            .or_else(|| env::current_dir().ok())
            .unwrap_or_else(|| PathBuf::from("."));

        let backend_host =
            env::var("KNOT_BACKEND_HOST").unwrap_or_else(|_| "127.0.0.1".to_string());
        let backend_port = env::var("KNOT_BACKEND_PORT").unwrap_or_else(|_| "7768".to_string());
        let backend_url = format!("http://{backend_host}:{backend_port}");

        let frontend_url = env::var("KNOT_FRONTEND_URL")
            .ok()
            .map(FrontendTarget::External)
            .or_else(|| {
                let dist = env::var("KNOT_FRONTEND_DIST")
                    .ok()
                    .map(PathBuf::from)
                    .or_else(|| {
                        let candidate = workspace_dir.join("desktop").join("dist");
                        if candidate.exists() {
                            Some(candidate)
                        } else {
                            None
                        }
                    });

                dist.map(|dist| FrontendTarget::App(dist.join("index.html")))
            })
            .unwrap_or_else(|| FrontendTarget::External(DEFAULT_FRONTEND_URL.to_string()));

        let binary =
            env::var("KNOT_BACKEND_BINARY").unwrap_or_else(|_| DEFAULT_BACKEND_BINARY.to_string());
        let args = env::var("KNOT_BACKEND_ARGS")
            .ok()
            .map(|value| {
                value
                    .split_whitespace()
                    .map(|part| part.to_string())
                    .collect()
            })
            .unwrap_or_else(|| {
                vec![
                    "-m".to_string(),
                    "uvicorn".to_string(),
                    "api:app".to_string(),
                    "--host".to_string(),
                    backend_host.clone(),
                    "--port".to_string(),
                    backend_port.clone(),
                ]
            });

        Self {
            workspace_dir,
            frontend_url,
            backend: BackendCommand { binary, args },
            backend_url,
        }
    }
}

impl BackendProcess {
    fn stopped() -> Self {
        Self {
            child: None,
            pid: None,
        }
    }

    fn is_running(&self) -> bool {
        self.child.is_some()
    }

    fn stop(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        self.pid = None;
    }

    fn start(&mut self, config: &AppConfig) -> Result<(), String> {
        if port_is_open(&config.backend_url) {
            self.child = None;
            self.pid = None;
            return Ok(());
        }

        let mut command = Command::new(&config.backend.binary);
        command
            .args(&config.backend.args)
            .current_dir(&config.workspace_dir)
            .env("PYTHONUNBUFFERED", "1")
            .env("KNOT_BACKEND_HOST", backend_host(&config.backend_url))
            .env("KNOT_BACKEND_PORT", backend_port(&config.backend_url))
            .stdin(Stdio::null())
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit());

        let child = command.spawn().map_err(|err| {
            format!(
                "failed to start backend '{}': {err}",
                format_backend_command(&config.backend)
            )
        })?;

        self.pid = Some(child.id());
        self.child = Some(child);
        Ok(())
    }
}

impl Drop for BackendProcess {
    fn drop(&mut self) {
        self.stop();
    }
}

fn start_backend(config: &AppConfig, backend: &Mutex<BackendProcess>) -> Result<(), String> {
    let mut process = backend.lock().map_err(|_| "backend mutex poisoned")?;
    process.start(config)?;
    Ok(())
}

fn backend_status_from(pid: Option<u32>, config: &AppConfig) -> BackendStatus {
    BackendStatus {
        running: pid.is_some() || port_is_open(&config.backend_url),
        pid,
        url: config.backend_url.clone(),
        backend_command: format_backend_command(&config.backend),
    }
}

fn frontend_url_string(target: &FrontendTarget) -> String {
    match target {
        FrontendTarget::External(url) => url.clone(),
        FrontendTarget::App(path) => path.display().to_string(),
    }
}

fn format_backend_command(command: &BackendCommand) -> String {
    std::iter::once(command.binary.as_str())
        .chain(command.args.iter().map(|arg| arg.as_str()))
        .collect::<Vec<_>>()
        .join(" ")
}

fn locate_workspace_dir() -> Option<PathBuf> {
    let mut current = env::current_dir().ok()?;
    loop {
        if current.join("pyproject.toml").exists() || current.join("Inbox").exists() {
            return Some(current);
        }
        if !current.pop() {
            return None;
        }
    }
}

fn port_is_open(url: &str) -> bool {
    let addr = backend_socket_addr(url);
    TcpStream::connect_timeout(&addr, Duration::from_millis(150)).is_ok()
}

fn backend_socket_addr(url: &str) -> SocketAddr {
    let without_scheme = url.trim_start_matches("http://");
    without_scheme
        .parse()
        .unwrap_or_else(|_| SocketAddr::from(([127, 0, 0, 1], 7768)))
}

fn backend_host(url: &str) -> String {
    backend_socket_addr(url).ip().to_string()
}

fn backend_port(url: &str) -> String {
    backend_socket_addr(url).port().to_string()
}
