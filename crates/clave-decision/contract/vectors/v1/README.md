# Golden vectors, contract version 1

Each file holds the hex bytes of one CBOR message, with `#` comment lines and
whitespace ignored. A consumer checks its own decoder against these bytes and
the values below before it ever sees a live decision.

These files are frozen. Contract version 2 ships a `vectors/v2/` directory
beside this one and leaves this one untouched, because a vector that changes is
a vector that proves nothing.

## `nominal.hex`

A PET bottle resolved to a sorted channel, 215 bytes.

| Field | Value |
| --- | --- |
| `version` | 1 |
| `object` | 4815162342 |
| `class` | `Pet`, taxonomy `M-01` |
| `channel` | 3 |
| `pose.point.x_meters` | 0.412 |
| `pose.point.y_meters` | -0.085 |
| `pose.point.z_meters` | 0.031 |
| `pose.yaw_radians` | 1.047 |
| `pose.reference_time` | 9100000000 |
| `window.earliest` | 9000000000 |
| `window.latest` | 9250000000 |
| `confidence` | 0.94 |

## `rejected.hex`

An object resolved to the reject channel, 219 bytes. It is an ordinary
decision: a consumer reads it and acts on its channel exactly as it does for
`nominal.hex`.

| Field | Value |
| --- | --- |
| `version` | 1 |
| `object` | 4815162343 |
| `class` | `Residue`, taxonomy `M-11` |
| `channel` | 0 |
| `pose.point.x_meters` | 0.18 |
| `pose.point.y_meters` | 0.24 |
| `pose.point.z_meters` | 0.028 |
| `pose.yaw_radians` | -0.75 |
| `pose.reference_time` | 12400000000 |
| `window.earliest` | 12300000000 |
| `window.latest` | 12600000000 |
| `confidence` | 0.41 |

## `unknown-version.hex`

`nominal.hex` with its version field rewritten to 2. A consumer that
implements version 1 shall reject this message whole and read no field past
the version. A consumer that decodes it into a version 1 decision has a
tolerant reader and has broken the contract.
