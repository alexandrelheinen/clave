//! The one real transport: a Unix domain socket carrying one record per
//! decision.

use std::io::{self, ErrorKind};
use std::os::unix::net::UnixDatagram;
use std::path::Path;

use crate::error::TransportError;
use crate::sink::{DecisionSink, SendOutcome};

/// Sends one encoded decision as one datagram on an `AF_UNIX` socket.
///
/// Record boundaries come from the kernel rather than from a length prefix,
/// which removes the framing bug class a stream socket would introduce: a
/// consumer reads one decision per read and never reassembles a frame. An
/// `AF_UNIX` datagram socket is reliable and delivers in order on Linux, so
/// ordering is a property of the transport and not something the publisher has
/// to restore.
///
/// The socket is non-blocking. A full kernel buffer, a consumer that has
/// stopped reading, and a consumer that has gone all report
/// [`SendOutcome::WouldBlock`] rather than an error, so the pipeline keeps
/// running and the discard policy decides what happens to the frame.
#[derive(Debug)]
pub struct UnixDatagramSink {
    socket: UnixDatagram,
}

impl UnixDatagramSink {
    /// Wraps a socket and puts it in non-blocking mode.
    ///
    /// # Errors
    ///
    /// Returns the operating system error when the socket cannot be put in
    /// non-blocking mode.
    pub fn from_socket(socket: UnixDatagram) -> io::Result<Self> {
        socket.set_nonblocking(true)?;
        Ok(Self { socket })
    }

    /// Connects to a consumer listening on `path`.
    ///
    /// # Errors
    ///
    /// Returns the operating system error when the socket cannot be created,
    /// connected, or put in non-blocking mode.
    pub fn connect<P: AsRef<Path>>(path: P) -> io::Result<Self> {
        let socket = UnixDatagram::unbound()?;
        socket.connect(path)?;
        Self::from_socket(socket)
    }

    /// Returns a connected pair: the sink, and the socket a consumer reads.
    ///
    /// The pair needs no path and no listener, which is what lets the delivery
    /// contract be proved inside one test process with no hardware.
    ///
    /// # Errors
    ///
    /// Returns the operating system error when the pair cannot be created or
    /// put in non-blocking mode.
    pub fn pair() -> io::Result<(Self, UnixDatagram)> {
        let (producer, consumer) = UnixDatagram::pair()?;
        Ok((Self::from_socket(producer)?, consumer))
    }

    /// Returns the socket underneath, for a caller that needs to name it.
    #[must_use]
    pub const fn socket(&self) -> &UnixDatagram {
        &self.socket
    }
}

/// Returns whether this failure is a refusal the discard policy absorbs rather
/// than a fault the caller has to hear about.
fn is_refusal(error: &io::Error) -> bool {
    matches!(
        error.kind(),
        ErrorKind::WouldBlock
            | ErrorKind::Interrupted
            | ErrorKind::ConnectionRefused
            | ErrorKind::ConnectionReset
            | ErrorKind::BrokenPipe
            | ErrorKind::NotConnected
    )
}

impl DecisionSink for UnixDatagramSink {
    type Error = TransportError;

    fn try_send(&mut self, frame: &[u8]) -> Result<SendOutcome, Self::Error> {
        match self.socket.send(frame) {
            Ok(written) if written == frame.len() => Ok(SendOutcome::Sent),
            Ok(written) => Err(TransportError::PartialRecord {
                written,
                expected: frame.len(),
            }),
            Err(error) if is_refusal(&error) => Ok(SendOutcome::WouldBlock),
            Err(error) => Err(TransportError::Socket(error)),
        }
    }
}
