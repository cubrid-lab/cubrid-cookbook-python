# Docs-site MP4: real runs of the AI agent state recipes (01 state store, 04 agent loop).
# Run from the repository root with the recording venv active and CUBRID_* set
# (see demos/README.md). Output goes to the ignored .demo-artifacts/ staging dir.
Require python
Output .demo-artifacts/agent-state.mp4
Set Shell bash
Set FontFamily "DejaVu Sans Mono"
Set FontSize 15
Set Width 1340
Set Height 860
Set Theme "Catppuccin Mocha"
Set Framerate 25
Set TypingSpeed 35ms
Set WaitTimeout 20s

Hide
Type `test -x "$VIRTUAL_ENV/bin/python" || exit 1; export PATH="$VIRTUAL_ENV/bin:$PATH"; clear`
Enter
Sleep 300ms
Show

Type "# 1) Sessions, messages and tool calls stored in CUBRID (JSON + SET columns)"
Enter
Type "python templates/ai-agent/01_agent_state.py"
Sleep 300ms
Enter
Wait+Screen /Agent state management working/
Sleep 7s
Type "clear"
Enter
Type "# 2) Query -> think -> act -> observe loop; every turn and tool call is persisted"
Enter
Type "python templates/ai-agent/04_agent_loop.py"
Sleep 300ms
Enter
Wait+Screen /Agent loop working/
Sleep 14s
