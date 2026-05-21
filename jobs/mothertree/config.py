import os

# Hasura
HASURA_URL = os.environ.get("HASURA_URL", "http://hasura.mother-tree.svc.cluster.local:8080/v1/graphql")
HASURA_ADMIN_SECRET = os.environ.get("HASURA_ADMIN_SECRET", "")

# Scaleway Generative APIs
SCALEWAY_AI_BASE_URL = os.environ.get("SCALEWAY_AI_BASE_URL", "https://api.scaleway.ai/v1")
SCALEWAY_AI_API_KEY = os.environ.get("SCALEWAY_AI_API_KEY", "")

# Models
EXTRACTION_MODEL = os.environ.get("EXTRACTION_MODEL", "mistral-small-3.2-24b-instruct-2506")
GENERATION_MODEL = os.environ.get("GENERATION_MODEL", "qwen3.5-397b-a17b")
SCORING_MODELS = [
    os.environ.get("SCORING_MODEL_1", "devstral-2-123b-instruct-2512"),
    os.environ.get("SCORING_MODEL_2", "llama-3.3-70b-instruct"),
    os.environ.get("SCORING_MODEL_3", "gemma-3-27b-it"),
]
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "bge-multilingual-gemma2")

# Anthropic — interactive layer, extraction, triage, arbitration
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CONVERSATION_MODEL = os.environ.get("CONVERSATION_MODEL", "claude-sonnet-4-6")
FAST_MODEL = os.environ.get("FAST_MODEL", "claude-haiku-4-5-20251001")
DEEP_EXTRACTION_MODEL = os.environ.get("DEEP_EXTRACTION_MODEL", "claude-opus-4-6")
TRIAGE_MODEL = "claude-haiku-4-5-20251001"
ARBITRATION_MODEL = "claude-sonnet-4-6"

# Confidence thresholds
CONFIDENCE_AUTO_ACCEPT = float(os.environ.get("CONFIDENCE_AUTO_ACCEPT", "0.7"))
CONFIDENCE_AUTO_REJECT = float(os.environ.get("CONFIDENCE_AUTO_REJECT", "0.4"))
CONFIDENCE_DISAGREEMENT_SPREAD = float(os.environ.get("CONFIDENCE_DISAGREEMENT_SPREAD", "0.3"))

# Slack
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN", "")
SLACK_SIGNALS_CHANNEL = os.environ.get("SLACK_SIGNALS_CHANNEL", "signals")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
ORGANIZATION_NAME = os.environ.get("ORGANIZATION_NAME", "")
