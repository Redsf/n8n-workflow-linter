# Terminal demo for the README. Rebuild with:  vhs demo/demo.tape
# Requires VHS (https://github.com/charmbracelet/vhs) and this package installed: pip install -e .
Output demo/demo.gif
Require n8n-lint
Set Shell "bash"
Set FontFamily "JetBrains Mono"
Set FontSize 15
Set Width 1600
Set Height 700
Set Padding 28
Set Theme "Catppuccin Mocha"
Set WindowBar Colorful
Set TypingSpeed 35ms
Set Framerate 24

Hide
Type "cd demo && clear" Enter
Sleep 300ms
Show

Type "# Lint every n8n workflow export before it lands in main" Sleep 300ms Enter
Type `n8n-lint workflows/; echo "exit code: $?"` Sleep 400ms Enter
Sleep 5s
Type "# A clean workflow passes, so CI stays green" Sleep 300ms Enter
Type `n8n-lint workflows/lead_router.json; echo "exit code: $?"` Sleep 400ms Enter
Sleep 4s
