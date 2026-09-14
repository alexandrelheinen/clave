//! The runtime peer the Python side starts.
//!
//! Four paths and nothing else. The producer binds the decision and outcome
//! sockets first, then starts this, then sends proposals to the listen socket
//! and a zero-length datagram to stop it.

use clave_sitl::{RuntimeError, ServeConfig, serve};

fn main() -> Result<(), RuntimeError> {
    let counters = serve(&ServeConfig::from_arguments(std::env::args().skip(1))?)?;
    println!(
        "{}",
        serde_json::to_string(&counters).unwrap_or_else(|_| "{}".to_owned())
    );
    Ok(())
}
