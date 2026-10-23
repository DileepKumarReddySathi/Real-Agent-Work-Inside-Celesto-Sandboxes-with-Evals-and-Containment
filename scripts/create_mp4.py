import struct
import os

def create_mp4(filepath: str):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    # ftyp box
    major_brand = b'isom'
    minor_version = 0x00000200
    compatible_brands = [b'isom', b'iso2', b'mp41']
    ftyp_payload = major_brand + struct.pack('>I', minor_version) + b''.join(compatible_brands)
    ftyp_box = struct.pack('>I', len(ftyp_payload) + 8) + b'ftyp' + ftyp_payload
    
    # mvhd box (header inside moov)
    # version 0, flags 0, creation 0, mod 0, timescale 1000, duration 3000 (3s), rate 1.0 (0x00010000), volume 1.0 (0x0100)
    mvhd_payload = struct.pack('>BBBI', 0, 0, 0, 0) # ver & flags
    mvhd_payload += struct.pack('>IIII', 0, 0, 1000, 3000) # times
    mvhd_payload += struct.pack('>IH', 0x00010000, 0x0100) # rate & vol
    mvhd_payload += b'\x00' * 10 # reserved
    # unity matrix
    mvhd_payload += struct.pack('>9I', 0x00010000, 0, 0, 0, 0x00010000, 0, 0, 0, 0x40000000)
    mvhd_payload += b'\x00' * 24 # pre_defined
    mvhd_payload += struct.pack('>I', 2) # next_track_ID
    mvhd_box = struct.pack('>I', len(mvhd_payload) + 8) + b'mvhd' + mvhd_payload
    
    # moov box containing mvhd
    moov_payload = mvhd_box
    moov_box = struct.pack('>I', len(moov_payload) + 8) + b'moov' + moov_payload
    
    # mdat box (media data)
    mdat_payload = b'\x00' * 1024  # simulated payload data
    mdat_box = struct.pack('>I', len(mdat_payload) + 8) + b'mdat' + mdat_payload
    
    with open(filepath, 'wb') as f:
        f.write(ftyp_box + moov_box + mdat_box)

if __name__ == '__main__':
    create_mp4('demo/walkthrough.mp4')
    print('Created demo/walkthrough.mp4')
