# Terminal half of the docs-site dashboard MP4: the one-command Streamlit demo.
# Run from the repository root with the dashboard stack stopped (see demos/README.md).
# The waits for the CUBRID health check and the dashboard's pip install are cut
# (Hide/Show); every command shown runs for real.
Require docker
Require curl
Output .demo-artifacts/dashboard-terminal.mp4
Set Shell bash
Set FontFamily "DejaVu Sans Mono"
Set FontSize 16
Set Width 1280
Set Height 720
Set Theme "Catppuccin Mocha"
Set Framerate 25
Set TypingSpeed 35ms
Set WaitTimeout 300s

Hide
Type "clear"
Enter
Sleep 300ms
Show

Type "cd templates/dashboard"
Enter
Type "docker compose up -d"
Sleep 300ms
Enter
Sleep 3s
Hide
Wait+Screen /Container \S*(app|dashboard)\S*\s+(Started|Created)/
Show
Sleep 2s
Type "until curl -sf localhost:8501/_stcore/health > /dev/null; do sleep 2; done; echo 'Dashboard ready: http://localhost:8501'"
Sleep 300ms
Enter
Hide
Wait+Screen /(?m)^Dashboard ready: http/
Show
Sleep 4s
