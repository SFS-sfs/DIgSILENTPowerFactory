This project focuses on python scripts to assist in power system simulations using DigSILENT Power Factory.

To get started, make sure the installed python version on your PC is the same as the one being used on your PF application.

here is one of many ways to setup your digsilent env in vscode.

1. Install python with the same version as your PF (for PF21, install python 3.9: https://www.python.org/downloads/release/python-3913/)
2. Set up a virtual environment, commit this line on your vscode terminal:

    "{python installation path}" -m venv .venv

   example:

   "C:\Users\thinkpad\AppData\Local\Programs\Python\Python39\python.exe" -m venv .venv
4. Activate the virtual environment. commit this line:
   .venv\Scripts\activate
   Note: don't forget to set the Python interpreter to venv on the bottom right of your vscode workspace.
5. You must close your PF app first to run the code.
6. On every scripts, these lines of code must be run first:

   import sys

   sys.path.append(r"C:\Program Files\DIgSILENT\PowerFactory 2021 SP2\Python\3.9")

   import powerfactory as pf

   app = pf.GetApplicationExt()

Acknowledgement
Gemini and Clkaude AI were used to assist in code writing.
