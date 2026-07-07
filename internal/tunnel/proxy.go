package tunnel

import (
	"io"
	"net"
)

// proxyBoth copies bytes between a and b until either side closes.
// Both directions run concurrently; the first EOF/error tears the
// other half down via Close so we don't leak goroutines.
func proxyBoth(a, b net.Conn) {
	done := make(chan struct{}, 2)
	go func() {
		_, _ = io.Copy(a, b)
		_ = a.Close()
		done <- struct{}{}
	}()
	go func() {
		_, _ = io.Copy(b, a)
		_ = b.Close()
		done <- struct{}{}
	}()
	<-done
}
