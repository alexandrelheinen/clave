//! The socket loop: bind, receive, decide, answer.

use std::fs;
use std::os::unix::net::UnixDatagram;
use std::path::{Path, PathBuf};

use clave_publish::UnixDatagramSink;

use crate::config::RuntimeConfig;
use crate::error::RuntimeError;
use crate::service::{RunCounters, Service};

/// The largest datagram the runtime will read.
///
/// A proposal at version 1 is about 250 bytes. The room above that means a
/// later version that grows a field is still read whole, because a datagram
/// longer than the buffer is truncated silently rather than reported.
const RECEIVE_CAPACITY: usize = 65_536;

/// Where the four files the runtime needs live.
///
/// The producer binds the decision and outcome sockets before the runtime
/// starts, because connecting a datagram socket to a path nothing is listening
/// on fails immediately rather than waiting.
#[derive(Debug, Clone)]
pub struct ServeConfig {
    /// The envelope and routing policy, as JSON.
    pub config: PathBuf,
    /// Where the runtime binds and receives proposals.
    pub listen: PathBuf,
    /// Where published decisions are sent, in the contract's CBOR encoding.
    pub decisions: PathBuf,
    /// Where one outcome per proposal is sent, as JSON.
    pub outcomes: PathBuf,
}

impl ServeConfig {
    /// Reads the four paths from command line arguments.
    ///
    /// Every path is required. A missing one is named rather than defaulted,
    /// because a runtime that silently binds somewhere else is a runtime whose
    /// decisions nobody receives.
    ///
    /// # Errors
    ///
    /// Returns [`RuntimeError::Config`] naming the flag that is absent or the
    /// argument that is not recognized.
    pub fn from_arguments<I: IntoIterator<Item = String>>(
        arguments: I,
    ) -> Result<Self, RuntimeError> {
        let mut config = None;
        let mut listen = None;
        let mut decisions = None;
        let mut outcomes = None;
        let mut arguments = arguments.into_iter();
        while let Some(flag) = arguments.next() {
            let value = arguments.next().map(PathBuf::from);
            match flag.as_str() {
                "--config" => config = value,
                "--listen" => listen = value,
                "--decisions" => decisions = value,
                "--outcomes" => outcomes = value,
                other => {
                    return Err(RuntimeError::Config {
                        reason: format!("unrecognized argument {other}"),
                    });
                }
            }
        }
        let missing = |flag: &str| RuntimeError::Config {
            reason: format!("{flag} is required"),
        };
        Ok(Self {
            config: config.ok_or_else(|| missing("--config"))?,
            listen: listen.ok_or_else(|| missing("--listen"))?,
            decisions: decisions.ok_or_else(|| missing("--decisions"))?,
            outcomes: outcomes.ok_or_else(|| missing("--outcomes"))?,
        })
    }
}

/// Runs the loop until the producer sends a zero-length datagram.
///
/// An empty datagram is the stop signal. It carries no version and no fields,
/// so it cannot be confused with a proposal this build refuses to read, and
/// the runtime exits having published everything the transport would take.
///
/// # Errors
///
/// Returns [`RuntimeError::Config`] or [`RuntimeError::Unreadable`] when the
/// configuration cannot be loaded, and [`RuntimeError::Socket`] when a socket
/// cannot be bound, connected, or read. A datagram that is not a proposal is
/// none of these: it is reported to the producer and the loop continues.
pub fn serve(paths: &ServeConfig) -> Result<RunCounters, RuntimeError> {
    let config = RuntimeConfig::load(&paths.config)?;

    // A socket file left behind by an earlier run would make the bind fail.
    let _removed = fs::remove_file(&paths.listen);
    let listener = UnixDatagram::bind(&paths.listen).map_err(|error| socket("listen", &error))?;
    let sink =
        UnixDatagramSink::connect(&paths.decisions).map_err(|error| socket("decisions", &error))?;
    let outcomes = UnixDatagram::unbound().map_err(|error| socket("outcomes", &error))?;
    outcomes
        .connect(&paths.outcomes)
        .map_err(|error| socket("outcomes", &error))?;

    let mut service = Service::new(
        config.envelope().to_owned(),
        config.resolver().clone(),
        sink,
    );
    let mut buffer = vec![0_u8; RECEIVE_CAPACITY];
    loop {
        let read = listener
            .recv(&mut buffer)
            .map_err(|error| socket("listen", &error))?;
        if read == 0 {
            break;
        }
        let outcome = service.handle(&buffer[..read]);
        let mut encoded = serde_json::to_vec(&outcome).unwrap_or_else(|_| b"{}".to_vec());
        encoded.push(b'\n');
        // A producer that has stopped reading its outcome socket is not a
        // reason to stop deciding, so a refused send is dropped rather than
        // returned.
        let _sent = outcomes.send(&encoded);
    }

    let counters = service.counters();
    remove(&paths.listen);
    Ok(counters)
}

/// Names which socket failed, in the words the command line uses.
fn socket(role: &'static str, error: &std::io::Error) -> RuntimeError {
    RuntimeError::Socket {
        role,
        reason: error.to_string(),
    }
}

/// Removes a socket file, ignoring a path that is already gone.
fn remove(path: &Path) {
    let _removed = fs::remove_file(path);
}
