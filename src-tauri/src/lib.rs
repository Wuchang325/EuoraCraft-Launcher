use pyo3::prelude::*;

/// The pytauri extension module for EuoraCraft Launcher.
///
/// Loaded by Python's `pytauri` package via the entry point `pytauri.ext_mod`.
/// This module provides `builder_factory` and `context_factory` to the Python side.
#[pymodule(gil_used = false)]
#[pyo3(name = "_pytauri_ext")]
pub mod _pytauri_ext {
    use super::*;

    #[pymodule_init]
    fn init(module: &Bound<'_, PyModule>) -> PyResult<()> {
        pytauri::pymodule_export(
            module,
            // context_factory: create Tauri context from generate_context!
            |_args, _kwargs| Ok(tauri::generate_context!()),
            // builder_factory: create the default Tauri builder
            |_args, _kwargs| {
                let builder = tauri::Builder::default();
                Ok(builder)
            },
        )
    }
}
