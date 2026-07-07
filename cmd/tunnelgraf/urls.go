package main

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"github.com/denniswalker/tunnelgraf/internal/profile"
)

func newUrlsCmd(g *globalFlags) *cobra.Command {
	return &cobra.Command{
		Use:   "urls",
		Short: "Print URLs for every tunnel, keyed by id",
		RunE: func(cmd *cobra.Command, args []string) error {
			root, err := loadProfile(g)
			if err != nil {
				return err
			}
			entries := profile.Flatten(root, profile.FlattenOptions{})
			links := map[string][]string{}
			for _, e := range entries {
				switch {
				case e.HostsFileEntry != "":
					links[e.ID] = []string{fmt.Sprintf("%s://%s:%d", e.Protocol, e.HostsFileEntry, e.Port)}
				case len(e.HostsFileEntries) > 0:
					var urls []string
					for _, h := range e.HostsFileEntries {
						urls = append(urls, fmt.Sprintf("%s://%s:%d", e.Protocol, h, e.Port))
					}
					links[e.ID] = urls
				default:
					links[e.ID] = []string{fmt.Sprintf("%s://%s:%d", e.Protocol, e.Host, e.Port)}
				}
			}
			enc := json.NewEncoder(os.Stdout)
			enc.SetIndent("", "    ")
			return enc.Encode(links)
		},
	}
}
