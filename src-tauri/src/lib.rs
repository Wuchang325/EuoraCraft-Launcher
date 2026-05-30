use pyo3::prelude::*;

/// The pytauri extension module for EuoraCraft Launcher.
/// This is the bridge between Rust/Tauri and Python.
/// Python imports this via entry_points["pytauri"]["ext_mod"].
#[pymodule]
fn _pytauri_ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Register all pytauri bindings (Builder, App, Commands, Webview, etc.)
    // This is provided by the `pytauri` crate, which depends on `pytauri-core`.
    pytauri::pymodule_register(m)?;
    Ok(())
}
