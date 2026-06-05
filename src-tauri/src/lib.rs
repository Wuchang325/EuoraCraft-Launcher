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
            // In dev mode (TAURI_DEV=true), the context auto-uses devUrl from tauri.conf.json
            |_args, _kwargs| Ok(tauri::generate_context!()),
            // builder_factory: create a configured Tauri builder
            // Accepts kwargs: no_server, frontend_dist_dir, dev_url
            |_args, kwargs| {
                let builder = tauri::Builder::default();

                // Log kwargs if provided (for debugging)
                if let Some(kw) = kwargs {
                    if let Ok(item) = kw.get_item("dev_url") {
                        if let Some(val) = item {
                            if let Ok(url) = val.extract::<String>() {
                                if !url.is_empty() && url != "None" {
                                    // Dev URL is already compiled into the context
                                    // from tauri.conf.json, so we just note it here
                                }
                            }
                        }
                    }
                }

                Ok(builder)
            },
        )
    }
}
