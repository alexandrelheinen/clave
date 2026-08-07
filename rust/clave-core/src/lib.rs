//! CLAVE core — Phase 0 stub for auditable ring-buffer hot paths.
//!
//! Native FFI and RealSense/EtherCAT integration are out of scope for Phase 0.

#![deny(unsafe_op_in_unsafe_fn)]

/// Fixed-capacity sample ring that overwrites the oldest entry when full.
#[derive(Debug, Clone)]
pub struct SampleRing {
    buf: Vec<f32>,
    capacity: usize,
    head: usize,
    len: usize,
}

impl SampleRing {
    /// Creates a ring with the given capacity (must be > 0).
    pub fn new(capacity: usize) -> Self {
        assert!(capacity > 0, "capacity must be greater than zero");
        Self {
            buf: vec![0.0; capacity],
            capacity,
            head: 0,
            len: 0,
        }
    }

    /// Pushes a sample, overwriting the oldest when full.
    pub fn push(&mut self, sample: f32) {
        let index = (self.head + self.len) % self.capacity;
        if self.len < self.capacity {
            self.buf[index] = sample;
            self.len += 1;
        } else {
            self.buf[self.head] = sample;
            self.head = (self.head + 1) % self.capacity;
        }
    }

    /// Number of samples currently stored.
    pub fn len(&self) -> usize {
        self.len
    }

    /// Whether the ring holds no samples.
    pub fn is_empty(&self) -> bool {
        self.len == 0
    }

    /// Maximum number of samples the ring can hold.
    pub fn capacity(&self) -> usize {
        self.capacity
    }

    /// Returns samples in chronological order (oldest first).
    pub fn as_slice_ordered(&self) -> Vec<f32> {
        let mut out = Vec::with_capacity(self.len);
        for i in 0..self.len {
            out.push(self.buf[(self.head + i) % self.capacity]);
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn overwrite_when_full_keeps_newest() {
        let mut ring = SampleRing::new(3);
        ring.push(1.0);
        ring.push(2.0);
        ring.push(3.0);
        assert_eq!(ring.len(), 3);
        assert_eq!(ring.as_slice_ordered(), vec![1.0, 2.0, 3.0]);

        ring.push(4.0);
        assert_eq!(ring.len(), 3);
        assert_eq!(ring.as_slice_ordered(), vec![2.0, 3.0, 4.0]);

        ring.push(5.0);
        assert_eq!(ring.as_slice_ordered(), vec![3.0, 4.0, 5.0]);
    }

    #[test]
    fn empty_ring_reports_empty() {
        let ring = SampleRing::new(4);
        assert!(ring.is_empty());
        assert_eq!(ring.capacity(), 4);
    }
}
