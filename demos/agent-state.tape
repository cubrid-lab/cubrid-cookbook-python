# README GIF: a real run of templates/ai-agent/01_agent_state.py against CUBRID.
# Run from the repository root with the recording venv active and CUBRID_* set
# (see demos/README.md). Output goes to the ignored .demo-artifacts/ staging dir.
Require python
Output .demo-artifacts/demo-agent-state.gif
Set Shell bash
Set FontFamily "DejaVu Sans Mono"
Set FontSize 18
Set Width 1000
Set Height 480
Set Theme "Catppuccin Mocha"
Set Framerate 12
Set TypingSpeed 35ms
Set WaitTimeout 20s

# Re-export the recording venv in case a login profile reset PATH.
Hide
Type `test -x "$VIRTUAL_ENV/bin/python" || exit 1; export PATH="$VIRTUAL_ENV/bin:$PATH"; clear`
Enter
Sleep 300ms
Show

Type "python templates/ai-agent/01_agent_state.py"
Sleep 300ms
Enter
Wait+Screen /Agent state management working/
Sleep 6s
