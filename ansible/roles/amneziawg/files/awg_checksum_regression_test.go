//go:build linux

package tun

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"testing"

	"golang.org/x/sys/unix"
)

// These helpers do not call the production checksum or pseudo-header helpers.
// They construct the complete pseudo-header and use scalar network-order words.
func zeroReviewSum(b []byte) uint16 {
	var sum uint32
	for len(b) >= 2 {
		sum += uint32(binary.BigEndian.Uint16(b))
		b = b[2:]
	}
	if len(b) == 1 {
		sum += uint32(b[0]) << 8
	}
	for sum>>16 != 0 {
		sum = (sum & 0xffff) + (sum >> 16)
	}
	return uint16(sum)
}

func zeroReviewPseudo(pkt []byte, v6 bool, proto byte) []byte {
	start := 20
	if v6 {
		start = 40
	}
	n := len(pkt) - start
	if v6 {
		p := make([]byte, 40)
		copy(p, pkt[8:40])
		binary.BigEndian.PutUint32(p[32:], uint32(n))
		p[39] = proto
		return p
	}
	p := make([]byte, 12)
	copy(p, pkt[12:20])
	p[9] = proto
	binary.BigEndian.PutUint16(p[10:], uint16(n))
	return p
}

func zeroReviewRaw(pkt []byte, v6 bool, proto byte) uint16 {
	start := 20
	if v6 {
		start = 40
	}
	p := zeroReviewPseudo(pkt, v6, proto)
	p = append(p, pkt[start:]...)
	return ^zeroReviewSum(p)
}

func zeroReviewPacket(v6 bool, proto byte, payload []byte, seq uint32) ([]byte, int, int, int) {
	start, transportLen, csumOffset := 20, 8, 6
	if v6 {
		start = 40
	}
	if proto == unix.IPPROTO_TCP {
		transportLen, csumOffset = 20, 16
	}
	pkt := make([]byte, start+transportLen+len(payload))
	if v6 {
		pkt[0], pkt[6], pkt[7] = 0x60, proto, 64
		binary.BigEndian.PutUint16(pkt[4:], uint16(len(pkt)-40))
		copy(pkt[8:24], []byte{0x20, 1, 0x0d, 0xb8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1})
		copy(pkt[24:40], []byte{0x20, 1, 0x0d, 0xb8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2})
	} else {
		pkt[0], pkt[8], pkt[9] = 0x45, 64, proto
		binary.BigEndian.PutUint16(pkt[2:], uint16(len(pkt)))
		binary.BigEndian.PutUint16(pkt[4:], 200)
		copy(pkt[12:16], []byte{192, 0, 2, 1})
		copy(pkt[16:20], []byte{198, 51, 100, 2})
	}
	binary.BigEndian.PutUint16(pkt[start:], 37738)
	binary.BigEndian.PutUint16(pkt[start+2:], 53)
	if proto == unix.IPPROTO_TCP {
		binary.BigEndian.PutUint32(pkt[start+4:], seq)
		pkt[start+12], pkt[start+13] = 0x50, 0x10 // no FIN/PSH changes at split
		binary.BigEndian.PutUint16(pkt[start+14:], 4096)
	} else {
		binary.BigEndian.PutUint16(pkt[start+4:], uint16(transportLen+len(payload)))
	}
	copy(pkt[start+transportLen:], payload)
	return pkt, start, transportLen, csumOffset
}

// A two-byte payload word makes the independently computed checksum exactly zero.
func zeroReviewPayload(t *testing.T, v6 bool, proto byte, seq uint32, n int, zero bool) []byte {
	t.Helper()
	p := make([]byte, n)
	for i := 2; i < len(p); i++ {
		p[i] = byte(31 + i)
	}
	pkt, _, _, _ := zeroReviewPacket(v6, proto, p, seq)
	word := zeroReviewRaw(pkt, v6, proto)
	binary.BigEndian.PutUint16(p, word)
	pkt, _, _, _ = zeroReviewPacket(v6, proto, p, seq)
	if got := zeroReviewRaw(pkt, v6, proto); got != 0 {
		t.Fatalf("fixture is not zero: %04x", got)
	}
	if !zero {
		p[1] ^= 1
		pkt, _, _, _ = zeroReviewPacket(v6, proto, p, seq)
		if got := zeroReviewRaw(pkt, v6, proto); got == 0 || got == 0xffff {
			t.Fatalf("fixture lacks ordinary nonzero checksum: %04x", got)
		}
	}
	return p
}

func zeroReviewAssert(t *testing.T, pkt []byte, v6 bool, proto byte, raw uint16) {
	t.Helper()
	start, csumOffset := 20, 6
	if v6 {
		start = 40
	}
	if proto == unix.IPPROTO_TCP {
		csumOffset = 16
	}
	want := raw
	if proto == unix.IPPROTO_UDP && raw == 0 {
		want = 0xffff
	}
	if got := binary.BigEndian.Uint16(pkt[start+csumOffset:]); got != want {
		t.Errorf("wire checksum %04x; want %04x (raw %04x)", got, want, raw)
	}
	if got := zeroReviewRaw(pkt, v6, proto); got != 0 {
		t.Errorf("pseudo-header plus wire packet checksum %04x; want zero", got)
	}
}

func TestChecksumZeroReviewNone(t *testing.T) {
	for _, v6 := range []bool{false, true} {
		for _, proto := range []byte{unix.IPPROTO_UDP, unix.IPPROTO_TCP} {
			for _, zero := range []bool{false, true} {
				for _, n := range []int{6, 7} {
					t.Run(fmt.Sprintf("v6=%v/proto=%d/zero=%v/payload=%d", v6, proto, zero, n), func(t *testing.T) {
						payload := zeroReviewPayload(t, v6, proto, 1000, n, zero)
						pkt, start, _, csumOffset := zeroReviewPacket(v6, proto, payload, 1000)
						raw := zeroReviewRaw(pkt, v6, proto)
						// CHECKSUM_PARTIAL holds the uncomplemented pseudo-header sum.
						binary.BigEndian.PutUint16(pkt[start+csumOffset:], zeroReviewSum(zeroReviewPseudo(pkt, v6, proto)))
						if err := gsoNoneChecksum(pkt, uint16(start), uint16(csumOffset)); err != nil {
							t.Fatal(err)
						}
						zeroReviewAssert(t, pkt, v6, proto, raw)
					})
				}
			}
		}
	}
}

func TestChecksumZeroReviewSplit(t *testing.T) {
	for _, v6 := range []bool{false, true} {
		for _, proto := range []byte{unix.IPPROTO_UDP, unix.IPPROTO_TCP} {
			// -1: all ordinary nonzero; 0: one zero datagram; 1: later zero in
			// a three-segment train with an odd-sized, short final segment.
			for _, zeroAt := range []int{-1, 0, 1} {
				t.Run(fmt.Sprintf("v6=%v/proto=%d/zeroAt=%d", v6, proto, zeroAt), func(t *testing.T) {
					lengths := []int{7, 7, 3}
					if zeroAt == 0 {
						lengths = []int{7}
					}
					var combined []byte
					raws := make([]uint16, len(lengths))
					payloads := make([][]byte, len(lengths))
					for i, n := range lengths {
						seq := uint32(1000)
						if proto == unix.IPPROTO_TCP {
							seq += uint32(7 * i)
						}
						p := zeroReviewPayload(t, v6, proto, seq, n, i == zeroAt)
						payloads[i] = p
						pkt, _, _, _ := zeroReviewPacket(v6, proto, p, seq)
						raws[i] = zeroReviewRaw(pkt, v6, proto)
						combined = append(combined, p...)
					}
					in, start, transportLen, csumOffset := zeroReviewPacket(v6, proto, combined, 1000)
					kind := uint8(unix.VIRTIO_NET_HDR_GSO_UDP_L4)
					if proto == unix.IPPROTO_TCP {
						kind = unix.VIRTIO_NET_HDR_GSO_TCPV4
						if v6 {
							kind = unix.VIRTIO_NET_HDR_GSO_TCPV6
						}
					}
					hdr := virtioNetHdr{gsoType: kind, hdrLen: uint16(start + transportLen), gsoSize: 7, csumStart: uint16(start), csumOffset: uint16(csumOffset)}
					out := make([][]byte, len(lengths))
					sizes := make([]int, len(lengths))
					const pad = 13
					for i := range out {
						out[i] = bytes.Repeat([]byte{0xa5}, 1500)
					}
					count, err := gsoSplit(in, hdr, out, sizes, pad, v6)
					if err != nil {
						t.Fatal(err)
					}
					if count != len(lengths) {
						t.Fatalf("segment count %d; want %d", count, len(lengths))
					}
					for i, n := range lengths {
						if sizes[i] != start+transportLen+n {
							t.Fatalf("segment %d size %d", i, sizes[i])
						}
						if !bytes.Equal(out[i][:pad], bytes.Repeat([]byte{0xa5}, pad)) {
							t.Errorf("segment %d prefix changed", i)
						}
						pkt := out[i][pad : pad+sizes[i]]
						if !bytes.Equal(pkt[start+transportLen:], payloads[i]) {
							t.Errorf("segment %d payload changed", i)
						}
						if v6 {
							if got := int(binary.BigEndian.Uint16(pkt[4:])); got != sizes[i]-40 {
								t.Errorf("IPv6 length %d", got)
							}
						} else {
							if got := int(binary.BigEndian.Uint16(pkt[2:])); got != sizes[i] {
								t.Errorf("IPv4 length %d", got)
							}
							if zeroReviewSum(pkt[:20]) != 0xffff {
								t.Errorf("segment %d invalid IPv4 header checksum", i)
							}
						}
						if proto == unix.IPPROTO_UDP {
							if got := int(binary.BigEndian.Uint16(pkt[start+4:])); got != transportLen+n {
								t.Errorf("UDP length %d", got)
							}
						} else {
							if got := binary.BigEndian.Uint32(pkt[start+4:]); got != uint32(1000+7*i) {
								t.Errorf("TCP sequence %d", got)
							}
						}
						zeroReviewAssert(t, pkt, v6, proto, raws[i])
					}
				})
			}
		}
	}
}
