# cubrid-cookbook-python — AI agent state management demo
Output ../docs/demo-agent-state.gif
Set FontSize 16
Set Width 1200
Set Height 600
Set Theme "Catppuccin Mocha"
Set Shell bash

Type@50ms "pip install pycubrid"
Enter
Sleep 2s

Type@50ms "python3 templates/ai-agent/01_agent_state.py"
Enter
Sleep 3s

# Output shows:
# Session created: 1
# Conversation (4 messages):
#   [user] What are the top 5 products?
#   [assistant] I'll query the products table for you.
#   [tool] Query returned 5 rows
# Agent metadata: {'confidence': 0.95, 'model': 'demo'}
# Agent state management working

Type@30ms 'echo "CUBRID stores agent sessions, messages, and tool calls in JSON columns"'
Enter
Sleep 2s

Type@30ms 'echo "SET types for tagging | JSON for LLM I/O | FK for relationships"'
Enter
Sleep 2s
