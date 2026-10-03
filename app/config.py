OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "qwen3-vl:8b-instruct"

# Context window sent with every request. Ollama's default (4096 tokens) is
# too small for a report with screenshots. Every request uses the same value
# because Ollama reloads the model whenever it changes.
OLLAMA_CONTEXT_LENGTH = 16384
