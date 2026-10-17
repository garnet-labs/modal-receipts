# Carve go:embed'ed BPF ELF relocatable objects out of the jibril binary.
import os, struct, sys
data = open(sys.argv[1], 'rb').read(); outdir = sys.argv[2]; os.makedirs(outdir, exist_ok=True)
i = n = 0
while True:
    i = data.find(b'\x7fELF\x02\x01\x01', i)
    if i < 0: break
    e_type, e_machine = struct.unpack_from('<HH', data, i + 16)
    if e_type == 1 and e_machine == 247:
        e_shoff, = struct.unpack_from('<Q', data, i + 40); e_shentsize, e_shnum = struct.unpack_from('<HH', data, i + 58)
        end = i + e_shoff + e_shentsize * e_shnum
        if e_shnum and end <= len(data):
            open(f'{outdir}/obj{n:02d}.o', 'wb').write(data[i:end]); n += 1; i = end; continue
    i += 1
print(n)
