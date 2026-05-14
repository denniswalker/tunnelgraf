//go:build !windows

package main

import (
	"os"
	"os/signal"
	"syscall"
)

func subscribeWindowChange(ch chan<- os.Signal) {
	signal.Notify(ch, syscall.SIGWINCH)
}
