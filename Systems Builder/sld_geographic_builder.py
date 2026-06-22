import sys

# ==========================================
# 0. PATH CONFIGURATION & INITIALIZATION
# ==========================================
PF_PATH = r"C:\Program Files\DIgSILENT\PowerFactory 2021 SP2\Python\3.9"
if PF_PATH not in sys.path:
    sys.path.append(PF_PATH)

import powerfactory as pf

class GridBuilder:
    def __init__(self, app):
        self.app = app

    def _create_cubicle_with_switch(self, busbar, cub_name):
        """
        Creates a cubicle on the busbar equipped with a switch.
        Conforms to the single busbar display standard in DIgSILENT.
        """
        # 1. Create a cubicle in the busbar
        cubicle = busbar.CreateObject("StaCubic", cub_name)
        
        # 2. Create a Switch INSIDE the cubicle
        switch = cubicle.CreateObject("StaSwitch", f"SW_{cub_name}")
        
        # 3. Activate the switch (on_off = 1 means closed/connected)
        switch.on_off = 1
        
        return cubicle

    def create_mv_consumer_substation(self, target_grid, sub_name, gps_coord=None):
        """
        Function to manually create a Secondary Substation (ElmTrfstat) from scratch,
        complete with ONE 20kV Busbar and a Load connected via a switch.
        """
        if not target_grid:
            print(f"[ERROR] Invalid Target Grid. Failed to create Substation '{sub_name}'")
            return None, None

        print(f"[*] Creating Manual Secondary Substation '{sub_name}'...")
        
        substation = target_grid.CreateObject("ElmTrfstat", sub_name)
        if not substation:
            print("[ERROR] Failed to create ElmTrfstat object.")
            return None, None

        # Create ONE Main 20kV Busbar INSIDE the Substation
        main_bus = substation.CreateObject("ElmTerm", f"MainBus_{sub_name}")
        main_bus.uknom = 20.0

        # Create Load
        load = substation.CreateObject("ElmLod", f"Load_{sub_name}")
        
        # Connect the load to the busbar using a switched cubicle
        cub_load = self._create_cubicle_with_switch(main_bus, f"cub_load_{sub_name}")
        load.bus1 = cub_load
        
        # Set default active and reactive power
        load.plini = 1.0 
        load.qlini = 0.2

        # Assign GPS coordinates if provided
        if gps_coord:
            lat, lon = gps_coord
            substation.SetAttribute("GPSlat", lat)
            substation.SetAttribute("GPSlon", lon)

        print(f"[OK] Substation '{sub_name}' successfully created!")
        return substation, main_bus

    def create_terminal(self, target_grid, term_name, voltage_kv, usage=0, gps_coord=None):
        """Creates a Bus/Terminal (ElmTerm)."""
        if not target_grid: return None

        print(f"[*] Creating Terminal '{term_name}' (Voltage: {voltage_kv} kV)...")
        term = target_grid.CreateObject("ElmTerm", term_name)
        if not term: return None
            
        term.uknom = voltage_kv
        term.iUsage = usage
        
        if gps_coord:
            lat, lon = gps_coord
            term.SetAttribute("GPSlat", lat)
            term.SetAttribute("GPSlon", lon)
            
        return term

    def create_line(self, target_grid, line_name, term_i=None, term_j=None, length_km=None, gps_coords=None):
        """Creates a Transmission/Distribution Line (ElmLne)."""
        if not target_grid: return None

        line = target_grid.CreateObject('ElmLne', line_name)
        if not line: return None

        # Connect to Terminals using switched cubicles
        if term_i is not None and term_j is not None:
            # Use internal function to create cubicles that contain switches
            cub_i = self._create_cubicle_with_switch(term_i, f"cub_i_{line_name}")
            cub_j = self._create_cubicle_with_switch(term_j, f"cub_j_{line_name}")
            
            line.bus1 = cub_i
            line.bus2 = cub_j
            print(f"    -> [OK] '{line_name}' is connected between '{term_i.loc_name}' and '{term_j.loc_name}'.")

        if length_km is not None:
            line.dline = length_km

        if gps_coords:
            for idx, (lat, lon) in enumerate(gps_coords):
                line.SetAttribute(f"GPScoords:{idx}:0", lat)
                line.SetAttribute(f"GPScoords:{idx}:1", lon)

        print(f"[OK] Line '{line_name}' successfully processed!")
        return line


# ==========================================
# MAIN EXECUTION (EXAMPLE USAGE)
# ==========================================
if __name__ == "__main__":
    try:
        # 1. Initialize Application & Activate Project
        app = pf.GetApplicationExt()
        if not app: 
            raise Exception("Connection to PowerFactory Failed!")

        # Replace with your actual project name
        project_name = "YOUR PROJECT" 
        err = app.ActivateProject(project_name)
        if err:
            raise Exception(f"Failed to activate project: {project_name}")

        print(f"\n[INITIALIZED] Project '{project_name}' activated successfully.")

        # 2. Get the Target Grid (Network Data Folder)
        # Assumes the active grid is named "Grid" inside the "netdat" folder. Adjust if necessary.
        target_grid = app.GetProjectFolder("netdat").GetContents("Grid.ElmNet")[0]

        # 3. Instantiate the Utility Class
        builder = GridBuilder(app)

        print("\n" + "="*50)
        print(" STARTING GRID CONSTRUCTION")
        print("="*50)

        # 4. Create an external Grid Terminal (e.g., 20 kV)
        term_source = builder.create_terminal(
            target_grid=target_grid, 
            term_name="Main_Feeder_Bus", 
            voltage_kv=20.0, 
            gps_coord=(-8.5, 140.4)
        )

        # 5. Create a Consumer Substation with an internal load and busbar
        substation, sub_bus = builder.create_mv_consumer_substation(
            target_grid=target_grid, 
            sub_name="Substation_Merauke", 
            gps_coord=(-8.6, 140.5)
        )

        # 6. Create a Line connecting the Main Feeder Bus to the Substation's internal bus
        line1 = builder.create_line(
            target_grid=target_grid, 
            line_name="Line_Feeder_To_Substation", 
            term_i=term_source, 
            term_j=sub_bus, 
            length_km=15.5
        )

        # 7. Save all changes to the database
        app.WriteChangesToDb()
        
        print("\n" + "="*50)
        print("[FINISHED] Network components built and saved successfully!")
        print("="*50 + "\n")

    except Exception as e:
        print(f"\n[ABORTED] Process failed: {e}")
