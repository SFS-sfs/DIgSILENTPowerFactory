#Automate Distance Relay Settings on line

#NOTE: Only use this if your terminal is an ElmTerm element. Make sure the CT and PT devices are already made and configured in the same cubicle as the relay.
#Cannot be used if your opposite terminal is a substation element. For substation use distance_relay_substat.py instead.

import sys
import math
import cmath

# Ensure this path matches your DIgSILENT version
sys.path.append(r"C:\Program Files\DIgSILENT\PowerFactory 2021 SP2\Python\3.9")
import powerfactory as pf

app = pf.GetApplicationExt()
if not app:
    raise Exception("Connection to DIgSILENT Failed!")

app.ActivateProject("YOUR PROJECT NAME") 

# ==========================================
# 1. INIT COMPONENTS & CONNECTION
# ==========================================
line = app.GetCalcRelevantObjects("YOUR LINE TARGET.ElmLne")[0]
cubs = [line.GetAttribute(b) for b in ["bus1", "bus2"] if line.GetAttribute(b)]

# Get local cubicle (Bus 5) and remote
cub_loc = next((c for c in cubs if c.cterm.loc_name == "bus_trafo_150"), None)
cub_rem = next((c for c in cubs if c != cub_loc), None)

# Find Adjacent Line
adj_line = next((c.obj_id for c in cub_rem.cterm.GetContents("*.StaCubic") 
                 if c.obj_id and c.obj_id.GetClassName() == "ElmLne" and c.obj_id != line), None)

# ==========================================
# 2. IMPEDANCE PARAMETERS (WITHOUT CONVERSION)
# ==========================================
# Get Z1 Magnitude directly from the line's Resulting Values attribute
Zm = line.Z1
Za = adj_line.Z1 if adj_line else 0.0

# Impedance Angle (Tilt Angle) from X1 and R1 components
phi_deg = math.degrees(math.atan2(line.X1, line.R1))

# REMOVED z_ratio: DIgSILENT Relays will convert CT/VT ratios automatically!

# ==========================================
# 3. RELAY SETTINGS USING DICTIONARY
# ==========================================
# Config -> Zone: (Main Multiplier, Adj Multiplier, Tdelay)
zone_cfg = {
    1: (0.8, 0.0, 0.0), # Zone 1: 80% Main, 0% Adj, Instant (0s)
    2: (1.2, 0.0, 0.4), # Zone 2: 120% Main, 0% Adj, Delay 0.4s
    3: (1.0, 1.2, 0.8)  # Zone 3: 100% Main + 120% Adj, Delay 0.8s
}

# Create / Assign F21 Relay at Cubicle
relay = cub_loc.GetContents("*.ElmRelay")[0] if cub_loc.GetContents("*.ElmRelay") else cub_loc.CreateObject("ElmRelay", "F21_Distance")

# Assign F21 Polygonal Relay Type. Please check your path to the relay type folder.
if not relay.typ_id:
    direct_path = "Prot\\ProtRelay\\ProtGeneric\\F21 Distance Polygonal\\F21 Distance Polygonal.*"
    hasil = app.GetGlobalLibrary().GetContents(direct_path)
    relay_type = next((obj for obj in hasil if "Folder" not in obj.GetClassName()), None)
    
    if relay_type:
        relay.typ_id = relay_type
        print(f"[*] Relay Type Successfully Assigned: {relay_type.loc_name}")
    else:
        print("[ERROR] Relay type targeting failed! Check the internal path again.")
        sys.exit()

print("[*] Starting configuration of internal relay blocks (Primary Impedance Input)...")

# ==========================================
# 4. LOOP TO INJECT PARAMETERS INTO INTERNAL BLOCKS
# ==========================================
for blk in relay.GetContents():
    name = blk.loc_name.lower()
    
    # A. Turn off unused basic blocks
    if any(x in name for x in ["load encroachment", "starting backup"]):
        try: blk.outserv = 1
        except: pass
        continue

    # B. Measurement Block
    if name == "measurement":
        try:
            blk.SetAttribute("vnom", 100.0)
            print("    -> [OK] Measurement set to 100V")
        except: pass

    # C. Polarizing Block (Automatic K0 Calculation)
    if name == "polarizing":
        try:
            z1 = complex(line.R1, line.X1)
            z0 = complex(line.R0, line.X0)
            
            if abs(z1) > 0:
                k0_complex = (z0 - z1) / (3 * z1)
                k0_mag = abs(k0_complex)
                k0_angle = math.degrees(cmath.phase(k0_complex))
                
                blk.SetAttribute("k0", k0_mag)
                try: blk.SetAttribute("phik0", k0_angle)
                except: 
                    try: blk.SetAttribute("ak0", k0_angle)
                    except: blk.SetAttribute("angle", k0_angle)
                    
                print(f"    -> [OK] K0 Calculated & Set: {k0_mag:.4f} \u2220 {k0_angle:.2f} Deg")
        except Exception as e: 
            print(f"    -> [WARN] Failed to set K0: {e}")

    # D. Starting Block (Set ip2)
    if name == "starting":
        try:
            blk.SetAttribute("ip2", 1.20)
            print("    -> [OK] Starting ip2 set to 1.20 p.u.")
        except: pass

    # E. Polygonal Block (Main & Timer)
    if "polygonal" in name:
        try:
            parts = name.split()
            zone_num = int(parts[-2]) if "delay" in name else int(parts[-1])
            tipe_fasa = "Ph-E" if "ph-e" in name else "Ph-Ph"
            
            if zone_num in zone_cfg:
                if "delay" in name:
                    _, _, t_delay = zone_cfg[zone_num]
                    blk.outserv = 0
                    blk.SetAttribute("Tdelay", t_delay)
                    print(f"    -> [OK] Zone {zone_num} Timer ({tipe_fasa}) set to: {t_delay}s")
                else:
                    k_main, k_adj, _ = zone_cfg[zone_num]
                    
                    # CALCULATE PRIMARY Z DIRECTLY
                    z_pri = (Zm * k_main) + (Za * k_adj)
                    
                    blk.outserv = 0
                    blk.SetAttribute("cpXmax", z_pri)
                    blk.SetAttribute("cpRmax", z_pri)
                    blk.SetAttribute("phi", phi_deg)
                    print(f"    -> [OK] Zone {zone_num} ({tipe_fasa}) set to: Z_Primary = {z_pri:.4f} Ohm")
                    
            else:
                blk.outserv = 1
                jenis = "Timer" if "delay" in name else "Main"
                print(f"    -> [OK] Zone {zone_num} {jenis} ({tipe_fasa}) turned off (outserv=1)")
                
        except Exception as e:
            print(f"    -> [WARN] Failed to process {name}: {e}")

# ==========================================
# 5. SAVE AND FINISH
# ==========================================
app.WriteChangesToDb()
print(f"\n[*] Line Impedance Angle: {phi_deg:.2f} Deg")
print(f"[FINISHED] F21 Distance Relay at {line.loc_name} Successfully Configured!")
