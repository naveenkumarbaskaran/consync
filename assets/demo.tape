# VHS tape for consync demo GIF
# Run: vhs assets/demo.tape

Output assets/demo.gif
Set FontSize 14
Set Width 900
Set Height 500
Set Theme "Catppuccin Mocha"
Set Padding 20
Set TypingSpeed 40ms

# Setup: create a temp project directory
Type "mkdir -p /tmp/consync-demo && cd /tmp/consync-demo"
Enter
Sleep 500ms

# Step 1: Create a source CSV
Type "# Step 1: Create source CSV with constants"
Enter
Sleep 800ms
Type `printf "name,value,unit,description\nBRAKE_PRESSURE_MAX,250,bar,Max hydraulic pressure\nCAN_MSG_ID,0x1A3,,Brake CAN ID\nFILTER_CUTOFF,1200.5,Hz,Low-pass cutoff\nTEMP_OFFSET,-40,C,Sensor offset\n" > params.csv`
Enter
Sleep 500ms

# Step 2: Init consync
Type "# Step 2: Initialize consync"
Enter
Sleep 800ms
Type "consync init"
Enter
Sleep 1s

# Step 3: Configure for embedded
Type "# Step 3: Configure for embedded ECU"
Enter
Sleep 800ms
Type `printf "mappings:\n  - source: params.csv\n    target: ecu_params.h\n    direction: source_to_target\n    header_guard: ECU_PARAMS_H\n    output_style: const\n    static_const: true\n    typed_ints: true\n" > .consync.yaml`
Enter
Sleep 500ms

# Step 4: Sync
Type "# Step 4: Generate C header"
Enter
Sleep 800ms
Type "consync sync"
Enter
Sleep 1.5s

# Step 5: Show the generated output
Type "# Result:"
Enter
Sleep 500ms
Type "cat ecu_params.h"
Enter
Sleep 3s

# Step 6: Check sync status
Type "# Step 5: Verify sync"
Enter
Sleep 800ms
Type "consync check"
Enter
Sleep 1.5s

# Done
Type "# Done! One CSV -> type-safe C header with stdint.h"
Enter
Sleep 2s

