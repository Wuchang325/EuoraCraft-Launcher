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

        // Import the Python launcher module
        let launcher_mod = match py.import("launcher") {
            Ok(m) => m,
            Err(e) => {
                eprintln!("Failed to import Python launcher: {}", e);
                std::process::exit(1);
            }
        };

        // Call launcher.main() to start the app
        if let Err(e) = launcher_mod.call_method0("main") {
            eprintln!("Failed to run Python launcher: {}", e);
            std::process::exit(1);
        }
    });
}

fn get_app_root() -> PathBuf {
    let exe = env::current_exe().unwrap();
    let exe_dir = exe.parent().unwrap();
    
    // Binary in target/debug/ -> walk up to find Cargo.toml
    let mut dir = Some(exe_dir);
    while let Some(d) = dir {
        if d.join("src-tauri").join("Cargo.toml").exists() {
            // Found project root (parent of src-tauri/)
            return d.to_path_buf();
        }
        if d.join("Cargo.toml").exists() {
            // Cargo workspace root
            return d.to_path_buf();
        }
        dir = d.parent();
    }
    
    // Fallback: same directory as the exe
    exe_dir.to_path_buf()
}
