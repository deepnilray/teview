TEVIEW — Windows portable executable
====================================

1. Extract TEVIEW-Windows-x64.zip.
2. Open Command Prompt in the folder containing TEVIEW.exe.
3. Run: TEVIEW.exe --run ball
4. A browser window opens with the simulated experiment.
5. Output and editable experiments are stored in %USERPROFILE%\TEVIEW.

You can also double-click TEVIEW.exe to see the text menu in a console window.

Examples:
  TEVIEW.exe --run lamp
  TEVIEW.exe --run charges
  TEVIEW.exe --run combined
  TEVIEW.exe --init-custom
  TEVIEW.exe --run custom
  TEVIEW.exe --run ball --converge
  TEVIEW.exe --help

TEVIEW simulations are simplified model predictions. Replaying the same
result or obtaining time-step agreement does not scientifically validate it.

This executable is unsigned. Windows may warn you about software downloaded
from the Internet. Verify its provenance and hash before allowing execution.
Do not run untrusted Python extensions or experiment sources.
