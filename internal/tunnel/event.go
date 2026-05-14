package tunnel

import "time"

// EventKind classifies state transitions the Manager publishes to
// subscribers. The zero value is Connecting.
type EventKind int

const (
	// EventConnecting fires when a dial is about to start.
	EventConnecting EventKind = iota
	// EventConnected fires when an ssh.Client handshake completes.
	EventConnected
	// EventDown fires when a previously-connected client drops.
	EventDown
	// EventRetry fires when a reconnect attempt failed; Err is set.
	EventRetry
)

// Event is a single state transition for one node in the tree.
type Event struct {
	Kind   EventKind
	NodeID string
	Err    error
	At     time.Time
}

// String is a short human-readable label useful for logs and tests.
func (k EventKind) String() string {
	switch k {
	case EventConnecting:
		return "connecting"
	case EventConnected:
		return "connected"
	case EventDown:
		return "down"
	case EventRetry:
		return "retry"
	}
	return "unknown"
}
