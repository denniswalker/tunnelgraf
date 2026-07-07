package transfer

import "testing"

func TestParseSpec(t *testing.T) {
	tests := []struct {
		name     string
		src, dst string
		explicit string
		want     Spec
		wantErr  bool
	}{
		{
			name: "upload with id prefix on destination",
			src:  "./foo.txt", dst: "web:/tmp/foo.txt",
			want: Spec{TunnelID: "web", Local: "./foo.txt", Remote: "/tmp/foo.txt", Direction: Upload},
		},
		{
			name: "download with id prefix on source",
			src:  "web:/etc/hosts", dst: "./hosts",
			want: Spec{TunnelID: "web", Remote: "/etc/hosts", Local: "./hosts", Direction: Download},
		},
		{
			name: "explicit --tunnel-id with two bare paths treated as upload",
			src:  "./a", dst: "/tmp/a", explicit: "web",
			want: Spec{TunnelID: "web", Local: "./a", Remote: "/tmp/a", Direction: Upload},
		},
		{
			name: "explicit --tunnel-id overrides prefix on destination",
			src:  "./a", dst: "wrong:/tmp/a", explicit: "web",
			want: Spec{TunnelID: "web", Local: "./a", Remote: "/tmp/a", Direction: Upload},
		},
		{
			name: "two remote args rejected",
			src:  "a:/x", dst: "b:/y",
			wantErr: true,
		},
		{
			name: "two bare paths without --tunnel-id rejected",
			src:  "./a", dst: "./b",
			wantErr: true,
		},
		{
			name: "bare absolute path not treated as remote",
			src:  "/var/log/app.log", dst: "web:/tmp/app.log",
			want: Spec{TunnelID: "web", Local: "/var/log/app.log", Remote: "/tmp/app.log", Direction: Upload},
		},
		{
			name: "path with slash before colon stays local",
			src:  "./dir/file:backup", dst: "web:/tmp/x",
			want: Spec{TunnelID: "web", Local: "./dir/file:backup", Remote: "/tmp/x", Direction: Upload},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, err := ParseSpec(tc.src, tc.dst, tc.explicit)
			if tc.wantErr {
				if err == nil {
					t.Fatalf("expected error, got spec %+v", got)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if got != tc.want {
				t.Errorf("got %+v, want %+v", got, tc.want)
			}
		})
	}
}
