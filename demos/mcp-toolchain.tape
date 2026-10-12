# Docs-site MP4: a real run of templates/ai-agent/02_mcp_toolchain.py, which starts
# cubrid-mcp-server over stdio and calls its tools (no LLM or API key involved).
# Run from the repository root with the recording venv active and CUBRID_* set
# (see demos/README.md). Output goes to the ignored .demo-artifacts/ staging dir.
Require python
Output .demo-artifacts/mcp-toolchain.mp4
Set Shell bash
Set FontFamily "DejaVu Sans Mono"
Set FontSize 16
Set Width 1280
Set Height 720
Set Theme "Catppuccin Mocha"
Set Framerate 25
Set TypingSpeed 35ms
Set WaitTimeout 30s

Hide
Type `test -x "$VIRTUAL_ENV/bin/python" || exit 1; export PATH="$VIRTUAL_ENV/bin:$PATH"; clear`
Enter
Sleep 300ms
Show

Type "pip list 2>/dev/null | grep -i cubrid"
Sleep 300ms
Enter
Wait+Screen /cubrid-mcp-server +[0-9]/
Sleep 3s
Type "# Start cubrid-mcp-server over stdio, list its tools, call them, try a DROP"
Enter
Type "python templates/ai-agent/02_mcp_toolchain.py"
Sleep 300ms
Enter
Wait+Screen /MCP tool chain working/
Sleep 20s
