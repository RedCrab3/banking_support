# Banking Customer Support AI Agent using Multi-Agent Architecture

Applied Generative AI capstone - Divyabrata Das Gupta.
Repository: https://github.com/RedCrab3/banking_support

## Features
- LangChain classifier, feedback agent and ticket-query agent coordinated by LangGraph.
- SQLite tickets with unique six-digit IDs, validated statuses and customer-scoped lookups.
- Idempotent complaint creation when the same customer/request ID is retried.
- Persistent thread checkpoints, saved conversation history and execution traces.
- Demo support status controls with audit history and stale-update protection.
- Streamlit chat, ticket dashboard and saved evaluation dashboard.
- Feedback greetings on first response or after five minutes of inactivity.

## Setup
Tested in a Linux Vocareum lab with Python 3.10.2. Use Python 3.10 or later.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
```

On Windows, activate with `.venv\Scripts\Activate.ps1` in PowerShell.
`requirements.in` defines direct dependency ranges; `requirements.txt` records the
installed environment used for this project. The SQLite Python module is built in;
the LangGraph SQLite checkpointer is installed through requirements.

## API configuration
The application reads OPENAI_API_KEY and either OPENAI_API_BASE or OPENAI_BASE_URL.
The Vocareum lab supplies these variables. On another system, configure them for
an authorized OpenAI-compatible Chat Completions endpoint before launch.
Never commit API keys. The application does not automatically load a .env file.
Configured model: gpt-4o-mini. The gateway must support tool calling.

To test connectivity (billable API request):
```bash
python -m tests.check_connection
python -m tests.check_langchain
```

## Launch
```bash
python -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```
On your laptop open http://localhost:8501. In the hosted lab use its Streamlit
service link. Databases and their parent directory are created automatically.

## Tests and evaluation
```bash
python -m pytest -q
```
Unit tests use temporary databases and stub agents; they do not make model calls.
The developer reported 45 passing tests on 2026-10-07.

Live checks and evaluations use API credits:
```bash
python -m tests.check_workflow
python -m tests.check_memory
python -m evaluation.run_evaluation
python -m evaluation.run_challenge
```
Saved baseline: 17/17 functional submissions; mean latency 2.74 seconds.
Saved challenge: 14/14 functional submissions; mean latency 2.64 seconds;
4/4 memory scenario checks. Both runs recorded zero errors and fallbacks.
These are fixed-set results, not a general accuracy guarantee. Reports retain
prompt hashes and package versions; earlier reports predate greeting/UI polish.

## Demo
1. Select a demo customer and start a new conversation.
2. Send positive feedback; then submit a card-delivery complaint.
3. Ask `Is it resolved yet?` to retrieve the remembered ticket.
4. Update its status in My tickets > Demo support controls and query it again.
5. Restart the app and reopen the saved conversation.
6. Switch customers and verify the original ticket is not returned.
7. Open Evaluation to inspect saved results without API calls.

## Project structure
- agents/: model configuration, classifier, feedback and query agents.
- graph/: state, nodes, routing and SQLite checkpoint context manager.
- database/: ticket operations, status audit and conversation/execution history.
- ui/: evaluation display and greeting timeout logic.
- tests/: offline unit tests and explicit live API checks.
- evaluation/: datasets, runners, saved reports and qualitative review.
- app.py: Streamlit application.

## Storage and scope
Runtime files: data/banking_support.db and data/checkpoints.db. Preserve these
files to retain tickets, history and memory across application restarts. A lab
reset that removes files will remove this data. The source ZIP excludes databases,
credentials, the virtual environment and caches.
Customer profiles and the support operator are simulated. There is no login,
registration or authorization system. Customer filtering demonstrates scoped
access; it is not a security boundary against someone controlling the demo selector.
No transactions, refunds, account operations or general banking knowledge retrieval
are implemented. Memory remembers the most recently discussed ticket, not full
semantic conversation history. The five-minute greeting gap is a demo setting.
SQLite is suitable for this local capstone; production would need authentication,
access controls, retention policies, concurrency testing and deployment hardening.

## Review provenance
The qualitative response review is AI-assisted, not independent human scoring.
The submission README was expanded during packaging; application source is unchanged.
