// EuoraCraft Launcher - Tauri v2 + pytauri main entry
//
// This binary:
// 1. Sets up the Python interpreter
// 2. Imports the Python launcher module (python/launcher.py)
// 3. The Python code takes over from there (creates Tauri app, registers commands, runs UI)

use std::path::PathBuf;
use std::env;

use pyo3::types::PyAnyMethods;

fn main() {
    // Initialize the Python interpreter
    pyo3::prepare_freethreaded_python();

    // The Python launcher module will handle:
    // - Building the Tauri app via pytauri
    // - Registering command handlers
    // - Managing the app lifecycle
    // See: python/launcher.py

    let app_root = get_app_root();
    
    // Set env var so Python can find our extension module
    // This tells pytauri which distribution to load the ext_mod from
    env::set_var("_PYTAURI_DIST", "euoracraft-launcher");

    pyo3::Python::with_gil(|py| {
        // Add the python/ directory to sys.path
        let syspath = py.import("sys").unwrap().getattr("path").unwrap();
        let py_dir = app_root.join("python");
        syspath.call_method1("insert", (0, py_dir.to_str().unwrap())).unwrap();

        // Also add the src-tauri directory (for the .pyd extension module)
        let tauri_dir = app_root.join("src-tauri");
        syspath.call_method1("insert", (0, tauri_dir.to_str().unwrap())).unwrap();

        // Run the Python launcher
        if let Err(e) = py.import("launcher") {
            eprintln!("Failed to import Python launcher: {}", e);
            std::process::exit(1);
        }
    });
}

fn get_app_root() -> PathBuf {
    // In development, the binary runs from src-tauri/
    // In production, it's bundled with the app
    let exe = env::current_exe().unwrap();
    let exe_dir = exe.parent().unwrap();
    
    // Check if we're in development (cargo run)
    if exe_dir.join("Cargo.toml").exists() || exe_dir.join("../../Cargo.toml").exists() {
        // Development: app root is the project root
        exe_dir.parent().unwrap().to_path_buf()
    } else {
        // Production: app root is the same directory as the exe
        exe_dir.to_path_buf()
    }
}
