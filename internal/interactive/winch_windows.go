//go:build windows

package interactive

import "os"

// Windows consoles signal size changes through a different mechanism
// (ReadConsoleInput with WINDOW_BUFFER_SIZE_EVENT). Skip for now;
// resizing won't propagate to the remote until a user reconnects.
func subscribeWindowChange(_ chan<- os.Signal) {}
