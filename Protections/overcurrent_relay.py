#script to automate overcurrent protection on line in DigSILENT PF

import sys
sys.path.append(r"C:\Program Files\DIgSILENT\PowerFactory 2021 SP2\Python\3.9")
import powerfactory as pf

app = pf.GetApplicationExt()
if not app:
    raise Exception("Connection to DIgSILENT Failed!")

app.ActivateProject("YOUR PROJECT")

# ==========================================
# 1. EXECUTE LOAD FLOW
# ==========================================
print("[*] Executing Load Flow to get actual load current...")
ldf = app.GetFromStudyCase("ComLdf")
err = ldf.Execute()

if err != 0:
    print("[ERROR] Load Flow failed to converge! Please check your network.")
    sys.exit()

# ==========================================
# 2. GET LINE & SELECT CUBICLE (TERMINAL i/j)
# ==========================================
lines = app.GetCalcRelevantObjects("YOUR LINE.ElmLne")
if not lines:
    print("[ERROR] Line not found.")
    sys.exit()

line = lines[0]

# --- TERMINAL SELECTOR SWITCH ---
target_terminal = 'j' 

cub_loc = line.bus1 if target_terminal == 'i' else line.bus2

if not cub_loc:
    print(f"[ERROR] Terminal {target_terminal} on {line.loc_name} is not perfectly connected.")
    sys.exit()

# ==========================================
# 3. GET LOAD CURRENT (FROM LINE) & CT RATING
# ==========================================
# Determine current variable based on the selected terminal
var_current = "m:I:bus1" if target_terminal == 'i' else "m:I:bus2"

# Draw current directly from the Line object
i_load_ka = line.GetAttribute(var_current)

# Validate if attribute is empty (Load flow failed to record)
if i_load_ka is None:
    print(f"[ERROR] Failed to read current from {line.loc_name}. Ensure Load Flow was successful.")
    sys.exit()

i_load_a = i_load_ka * 1000.0
print(f"[*] Load Current at {line.loc_name} (Terminal {target_terminal}): {i_load_a:.2f} Amperes")

ct = cub_loc.GetContents("*.StaCt")
ct_pri = ct[0].ptapset if ct else 100.0
print(f"[*] Primary CT Reference used: {ct_pri} Amperes")

# ==========================================
# 4. CALCULATE & ASSIGN RELAY
# ==========================================
ipset_1_pu = (1.1 * i_load_a) / ct_pri 
ipset_2_pu = (10.0 * i_load_a) / ct_pri 

nama_bus = cub_loc.cterm.loc_name if cub_loc.cterm else "Unknown_Bus"
relay_name = f"F50_51_OCR_{target_terminal}"

relay = cub_loc.GetContents("*.ElmRelay")[0] if cub_loc.GetContents("*.ElmRelay") else cub_loc.CreateObject("ElmRelay", relay_name)

if not relay.typ_id:
    direct_path = "Prot\\ProtRelay\\ProtGeneric\\F50_F51 Phase overcurrent\\F50_F51 Phase overcurrent.*"
    hasil = app.GetGlobalLibrary().GetContents(direct_path)
    relay_type = next((obj for obj in hasil if "Folder" not in obj.GetClassName()), None)
    
    if relay_type:
        relay.typ_id = relay_type
        print(f"[*] Relay Type Successfully Assigned: {relay_type.loc_name}")
    else:
        print("[ERROR] Failed to retrieve relay type! Check the library path again.")
        sys.exit()

print(f"\n[*] Injecting settings into Relay at {nama_bus}...")

# ==========================================
# 5. LOOPING TO INJECT INTERNAL BLOCK PARAMETERS
# ==========================================
for blk in relay.GetContents():
    name = blk.loc_name.lower()
    
    # A. Turn off specific blocks: I>>>, I>>>>, Directional, Earth, Logic, I0
    if name in ["i>>>", "i>>>>"] or any(x in name for x in ["dir", "earth", "i0"]):
        try: 
            blk.outserv = 1
            if name in ["i>>>", "i>>>>"]:
                print(f"    -> [OK] Block {blk.loc_name} turned off (outserv=1)")
        except: pass
        continue

    # B. Configure Stage 1 (I>)
    if name == "i>":
        try:
            blk.outserv = 0
            blk.SetAttribute("Ipset", ipset_1_pu)
            blk.SetAttribute("Tpset", 0.2)
            try: blk.SetAttribute("curvetype", "IEEE Inverse") 
            except: pass
            print(f"    -> [OK] I> set: Ipset = {ipset_1_pu:.4f} p.u., Time Dial = 0.2 (IEEE Inverse)")
        except Exception as e:
            print(f"    -> [WARN] Failed to set I>: {e}")

    # C. Configure Stage 2 (I>>)
    elif name == "i>>":
        try:
            blk.outserv = 0
            blk.SetAttribute("Ipset", ipset_2_pu)
            blk.SetAttribute("Tpset", 0.0) 
            print(f"    -> [OK] I>> set: Ipset = {ipset_2_pu:.4f} p.u., Delay = 0.0s (Definite)")
        except Exception as e:
            print(f"    -> [WARN] Failed to set I>>: {e}")

    # D. Measurement Block (Ensure it stays active)
    elif "measurement" in name:
        try: 
            blk.outserv = 0
            print(f"    -> [OK] Measurement ({blk.loc_name}) ensured active (outserv=0)")
        except: pass

    elif "logic" in name:
        try: 
            blk.outserv = 0
            print(f"    -> [OK] Logic ({blk.loc_name}) ensured active (outserv=0)")
        except: pass

app.WriteChangesToDb()
print("\n[FINISHED] OCR Relay automation successfully executed!")
