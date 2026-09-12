# cubrid-cookbook-python — MCP tool chain demo (programmatic, no Claude)
Output ../docs/demo-mcp-toolchain.gif
Set FontSize 16
Set Width 1200
Set Height 600
Set Theme "Catppuccin Mocha"
Set Shell bash

Type@50ms "pip install pycubrid cubrid-mcp-server"
Enter
Sleep 3s

Type@50ms "python3 templates/ai-agent/02_mcp_toolchain.py"
Enter
Sleep 3s

# Output shows:
# MCP tool chain demo — querying CUBRID via MCP protocol
#   Server: cubrid-mcp-server
#   Available tools (12):
#     - all_table_names: Return every user table...
#     - execute_query: Execute a read-only SQL...
#   Tables in database (N): [table1, table2, ...]
#   DROP TABLE rejected by read-only whitelist: True
# MCP tool chain working

Type@30ms 'echo "Read-only whitelist protects against unintended writes"'
Enter
Sleep 2s

Type@30ms 'echo "12 MCP tools | JSON columns for LLM I/O | SET types for collections"'
Enter
Sleep 2s
