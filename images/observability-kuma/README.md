# Private observer image

This image keeps Uptime Kuma 2.5.9 and its published application files. It updates
security fixes through the committed production dependency lock and exact Debian
package versions. It retains only the unchanged upstream SQLite native binding,
not its old JavaScript dependency tree. Optional packages and build-only package
managers are not installed in the runtime. The unused Apprise/Python and SQLite
CLI packages are removed; the Node SQLite binding remains. Cloudflared is absent: administration
must stay private.

The upstream health probe is rebuilt with Go 1.27.3 and normal TLS verification.
`LICENSE.upstream` covers the upstream files. The Dockerfile pins both base image
indexes. The publisher builds each native architecture, loads SQLite, and rejects
fixed HIGH/CRITICAL findings before publishing. Runtime roles consume only the
verified architecture digests, never the build tag. An image update also requires
the role's quiesced encrypted backup and isolated application restore test.

The role pins the runnable child manifest for each architecture. The publisher
retains the attested index as provenance and verifies that the published child
has the same image configuration as the locally scanned build.
