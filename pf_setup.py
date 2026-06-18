import sys

class PowerFactoryEnvironment:
    def __init__(self, pf_path=r"C:\Program Files\DIgSILENT\PowerFactory 2021 SP2\Python\3.9"):
        """
        Initializes the connection to the DIgSILENT engine.
        """
        if pf_path not in sys.path:
            sys.path.append(pf_path)
            
        import powerfactory as pf
        self.app = pf.GetApplicationExt()
        
        if not self.app:
            raise Exception("Connection to DIgSILENT failed!")
        print("[*] PowerFactory API Connected.")

    def activate_project(self, project_name):
        err = self.app.ActivateProject(project_name)
        if err == 0:
            print(f"[OK] Project '{project_name}' activated.")
            return True # <-- ADD RETURN TRUE IF SUCCESSFUL
        else:
            print(f"[ERROR] Failed to activate project '{project_name}'.")
            return False # <-- ADD RETURN FALSE IF FAILED

    def _activate_object(self, folder_type, obj_name, ext):
        """
        Internal function to find and activate an object based on its folder type.
        """
        folder = self.app.GetProjectFolder(folder_type)
        if not folder:
            print(f"[ERROR] System folder '{folder_type}' not found.")
            return None # <-- RETURN NONE
        
        objects = folder.GetContents(f"{obj_name}.{ext}", 1)
        if objects:
            objects[0].Activate()
            print(f"[OK] {obj_name} ({ext}) successfully activated.")
            return objects[0] # <-- RETURN THE OBJECT SO IT CAN BE USED IF NEEDED
        else:
            print(f"[ERROR] '{obj_name}' not found in folder {folder_type}.")
            return None # <-- RETURN NONE

    # FORWARD THE RETURNS FROM THE INTERNAL FUNCTION TO MAIN FUNCTIONS
    def activate_study_case(self, case_name):
        return self._activate_object("study", case_name, "IntCase")

    def activate_grid(self, grid_name):
        return self._activate_object("netdat", grid_name, "ElmNet")

    def activate_network_variation(self, var_name):
        return self._activate_object("netvar", var_name, "IntScheme")

    def activate_scenario(self, scen_name):
        return self._activate_object("scen", scen_name, "IntScenario")

    def setup_full(self, project, study_case=None, grid=None, net_var=None, scenario=None):
        """
        "All-in-One" Shortcut: Execute all activations in a single line.
        """
        print("-" * 40)
        
        # Check if the project was successfully activated
        if not self.activate_project(project):
            return None # Stop setup if project activation fails
            
        if study_case: self.activate_study_case(study_case)
        if grid: self.activate_grid(grid)
        if net_var: self.activate_network_variation(net_var)
        if scenario: self.activate_scenario(scenario)
        print("-" * 40)

        return self.app

    def get_grid_object(self, grid_name):
        """
        Finds and RETURNS the ElmNet (Grid) object without having to activate it.
        Very useful for topology injection in the background.
        """
        folder = self.app.GetProjectFolder("netdat")
        if not folder:
            print("[ERROR] Network Data folder not found.")
            return None
            
        grids = folder.GetContents(f"{grid_name}.ElmNet", 1)
        if grids:
            return grids[0]
        else:
            print(f"[ERROR] Grid named '{grid_name}' not found.")
            return None
            
        # Note: The 'return self.app' line below has been removed because it was dead-code
