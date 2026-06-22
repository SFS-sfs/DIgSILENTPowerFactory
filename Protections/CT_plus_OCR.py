import sys
import math

# Ensure this path matches your DIgSILENT version
sys.path.append(r"C:\Program Files\DIgSILENT\PowerFactory 2021 SP2\Python\3.9")
import powerfactory as pf

class ProtectionAutomator:
    def __init__(self, project_name):
        """Initializes the connection to PowerFactory and activates the project."""
        self.app = pf.GetApplicationExt()
        if not self.app:
            raise Exception("Connection to DIgSILENT Failed!")
        
        err = self.app.ActivateProject(project_name)
        if err:
            raise Exception(f"Failed to activate project: {project_name}")
        
        print(f"[INITIALIZED] Successfully connected to project: {project_name}")

    def get_target_cubicle(self, line_name, target_terminal='i'):
        """Retrieves the line, target cubicle, and its nominal current."""
        lines = self.app.GetCalcRelevantObjects(f"{line_name}.ElmLne")
        if not lines:
            raise ValueError(f"Line '{line_name}' not found.")
        
        line = lines[0]
        cub = line.bus1 if target_terminal == 'i' else line.bus2

        if not cub:
            raise ValueError(f"Terminal '{target_terminal}' on {line.loc_name} is not perfectly connected.")

        if not line.typ_id:
            raise ValueError(f"Line {line.loc_name} has no type. Current rating cannot be read.")

        i_nom = line.typ_id.sline * 1000
        return line, cub, i_nom

    def install_ct(self, cubicle, line_name, i_nom):
        """Calculates CT rating, creates/finds CT type, and installs the CT object."""
        # 1. CT Rating Calculation
        std_ct = [50, 100, 150, 200, 250, 300, 400, 500, 600, 800, 1000, 1200, 1500, 2000, 3000] 
        ct_pri = next((r for r in std_ct if r >= i_nom), math.ceil(i_nom/500) * 500)
        ct_sec = 1.0
        
        # 2. Find or Create CT Type
        lib = self.app.GetProjectFolder("equip")
        ct_type = None

        for t in lib.GetContents("*.TypCt"):
            p_taps = t.GetAttribute("primtaps")
            s_taps = t.GetAttribute("sectaps")
            
            if p_taps and s_taps:
                p_taps_list = [float(x) for x in p_taps]
                s_taps_list = [float(x) for x in s_taps]
                
                if float(ct_pri) in p_taps_list and ct_sec in s_taps_list:
                    ct_type = t
                    print(f"[*] CT Type '{t.loc_name}' found in the Library.")
                    break

        if not ct_type:
            type_name = f"CT Type {int(ct_pri)}/{int(ct_sec)}A"
            print(f"[*] Creating new CT Type: {type_name}")
            ct_type = lib.CreateObject("TypCt", type_name)
            ct_type.SetAttribute("primtaps", [float(ct_pri)])
            ct_type.SetAttribute("sectaps", [ct_sec])

        # 3. Create CT Object
        bus_name = cubicle.cterm.loc_name if cubicle.cterm else "Unknown_Bus"
        ct_name = f"CT_{line_name}"

        print(f"[*] Creating new CT {ct_name} at {bus_name}...")
        ct_obj = cubicle.CreateObject("StaCt", ct_name)
        ct_obj.typ_id = ct_type
        ct_obj.ptapset = float(ct_pri)
        ct_obj.stapset = ct_sec

        return ct_pri, ct_sec

    def calculate_max_short_circuit(self, target_bus):
        """Executes 3-phase and 1-phase short circuits to find maximum fault current."""
        print("[*] Executing Short Circuit calculation (3-Phase & 1-Phase)...")
        shc = self.app.GetFromStudyCase("ComShc")
        shc.shcobj = target_bus

        # 3-Phase SC
        shc.iopt_shc = "3ph" 
        err_shc3 = shc.Execute()
        ikss_3ph_ka = target_bus.GetAttribute("m:Ikss") if err_shc3 == 0 else 0.0

        # 1-Phase to Ground SC
        shc.iopt_shc = "1phE" 
        err_shc1 = shc.Execute()
        ikss_1ph_ka = target_bus.GetAttribute("m:Ikss") if err_shc1 == 0 else 0.0

        isc_max_a = max(ikss_3ph_ka, ikss_1ph_ka) * 1000.0
        return isc_max_a

    def install_ocr_relay(self, cubicle, line_name, i_nom, ct_pri, isc_max_a):
        """Calculates OCR settings and injects them into a newly created relay."""
        # 1. Setting Calculation
        ipset_1_pu = (1.1 * i_nom) / ct_pri 
        isc_ratio = isc_max_a / ct_pri
        ipset_2_pu = 20.0 if isc_ratio > 10.0 else 10.0

        bus_name = cubicle.cterm.loc_name if cubicle.cterm else "Unknown_Bus"
        relay_name = f"{line_name}_OCR_protection"

        # 2. Create Relay and Assign Type
        print(f"[*] Creating new Relay {relay_name} at {bus_name}...")
        relay = cubicle.CreateObject("ElmRelay", relay_name)

        if not relay.typ_id:
            direct_path = "Prot\\ProtRelay\\ProtGeneric\\F50_F51 Phase overcurrent\\F50_F51 Phase overcurrent.*"
            result = self.app.GetGlobalLibrary().GetContents(direct_path)
            relay_type = next((obj for obj in result if "Folder" not in obj.GetClassName()), None)
            
            if relay_type:
                relay.typ_id = relay_type
                print(f"[*] Relay Type Successfully Assigned: {relay_type.loc_name}")
            else:
                raise Exception("[ERROR] Failed to retrieve relay type! Check the library path.")

        # 3. Inject Parameters into Blocks
        print(f"[*] Injecting settings to Relay at {bus_name}...")
        for blk in relay.GetContents():
            name = blk.loc_name.lower()
            
            if name in ["i>>>", "i>>>>"] or any(x in name for x in ["dir", "earth", "i0"]):
                try: 
                    blk.outserv = 1
                    if name in ["i>>>", "i>>>>"]:
                        print(f"    -> [OK] Block {blk.loc_name} is deactivated (outserv=1)")
                except: pass
                continue

            if name == "i>":
                try:
                    blk.outserv = 0
                    blk.SetAttribute("Ipset", ipset_1_pu)
                    blk.SetAttribute("Tpset", 0.4) 
                    try: blk.SetAttribute("curvetype", "IEC Standard Inverse") 
                    except: pass
                    print(f"    -> [OK] I> set: Ipset = {ipset_1_pu:.4f} p.u., Time Dial = 0.4 (Standard Inverse)")
                except Exception as e:
                    print(f"    -> [WARN] Failed to set I>: {e}")

            elif name == "i>>":
                try:
                    blk.outserv = 0
                    blk.SetAttribute("Ipset", ipset_2_pu) 
                    blk.SetAttribute("Tpset", 0.0) 
                    print(f"    -> [OK] I>> set: Ipset = {ipset_2_pu:.4f} p.u., Delay = 0.0s (Definite)")
                except Exception as e:
                    print(f"    -> [WARN] Failed to set I>>: {e}")

            elif "measurement" in name or "logic" in name:
                try: 
                    blk.outserv = 0
                    print(f"    -> [OK] {blk.loc_name} ensured active (outserv=0)")
                except: pass

    def run_automation(self, target_line_name, terminal='i'):
        """Main method to execute the entire protection setup workflow."""
        try:
            print("\n" + "="*50)
            print(f" STARTING PROTECTION AUTOMATION FOR: {target_line_name}")
            print("="*50)

            # Step 1: Get Cubicle
            line, cub, i_nom = self.get_target_cubicle(target_line_name, terminal)
            print(f"[*] Line Current Rating Capacity: {i_nom:.2f} Amperes")

            # Step 2: Install CT
            ct_pri, ct_sec = self.install_ct(cub, target_line_name, i_nom)

            # Step 3: Run Short Circuit
            target_bus = cub.cterm
            isc_max_a = self.calculate_max_short_circuit(target_bus)
            print(f"    -> Maximum Isc: {isc_max_a:.2f} Amperes")
            print(f"    -> Isc/CT Ratio: {isc_max_a / ct_pri:.2f}")

            # Step 4: Install Relay
            self.install_ocr_relay(cub, target_line_name, i_nom, ct_pri, isc_max_a)

            # Step 5: Save
            self.app.WriteChangesToDb()
            print("\n[FINISHED] OCR Relay Automation successfully executed!")
            print("="*50 + "\n")

        except Exception as e:
            print(f"\n[ABORTED] Process failed: {e}")


# ==========================================
# MAIN EXECUTION BLOCK
# ==========================================
if __name__ == "__main__":
    PROJECT_NAME = "YOUR PROJECT"
    TARGET_LINE = "YOUR LINE"
    TARGET_TERMINAL = "i"

    # Instantiate the class and run the workflow
    automator = ProtectionAutomator(PROJECT_NAME)
    automator.run_automation(TARGET_LINE, TARGET_TERMINAL)
