//! The in-memory sink the tests and the property runs drive.

use crate::sink::{DecisionSink, SendOutcome};

/// The failure an [`InMemorySink`] reports when it is asked to fault.
#[derive(Debug, Clone, Copy, PartialEq, Eq, thiserror::Error)]
#[error("the in-memory sink is set to fault")]
pub struct SinkFault;

/// What an [`InMemorySink`] does with the next frame.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
enum Mode {
    /// Take every frame.
    #[default]
    Accepting,
    /// Take nothing, the way a transport behaves when nobody is reading.
    Refusing,
    /// Fail, the way a transport behaves when it is broken.
    Faulting,
}

/// A sink that keeps frames in memory instead of sending them anywhere.
///
/// It exists so that the discard policy, the counters, and the ordering
/// contract can be proved with no syscalls, and so that a consumer that never
/// reads can be simulated without one.
#[derive(Debug, Default)]
pub struct InMemorySink {
    frames: Vec<Vec<u8>>,
    mode: Mode,
}

impl InMemorySink {
    /// Returns a sink that takes every frame.
    #[must_use]
    pub fn new() -> Self {
        Self::default()
    }

    /// Returns a sink that takes nothing, standing in for a consumer that has
    /// stopped reading.
    #[must_use]
    pub fn refusing() -> Self {
        Self {
            frames: Vec::new(),
            mode: Mode::Refusing,
        }
    }

    /// Returns a sink that fails, standing in for a broken transport.
    #[must_use]
    pub fn faulting() -> Self {
        Self {
            frames: Vec::new(),
            mode: Mode::Faulting,
        }
    }

    /// Starts taking frames again.
    pub fn accept(&mut self) {
        self.mode = Mode::Accepting;
    }

    /// Stops taking frames.
    pub fn refuse(&mut self) {
        self.mode = Mode::Refusing;
    }

    /// Returns every frame this sink took, in the order it took them.
    #[must_use]
    pub fn frames(&self) -> &[Vec<u8>] {
        &self.frames
    }
}

impl DecisionSink for InMemorySink {
    type Error = SinkFault;

    fn try_send(&mut self, frame: &[u8]) -> Result<SendOutcome, Self::Error> {
        match self.mode {
            Mode::Accepting => {
                self.frames.push(frame.to_vec());
                Ok(SendOutcome::Sent)
            }
            Mode::Refusing => Ok(SendOutcome::WouldBlock),
            Mode::Faulting => Err(SinkFault),
        }
    }
}
