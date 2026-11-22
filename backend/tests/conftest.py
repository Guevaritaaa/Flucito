"""La regresión usa credenciales falsas incluso si el desarrollador configuró .env.

Las pruebas de aceptación reales se ejecutan por separado, explícitamente.
Configurar antes de importar la aplicación impide capturar clientes de producción.
"""

import os

os.environ["OPENAI_API_KEY"] = "clave-openai-de-prueba"
os.environ["GROQ_API_KEY"] = "clave-groq-de-prueba"
os.environ["OPENAI_MODEL"] = "gpt-5.6-luna"
os.environ["LLM_PRIMARY_PROVIDER"] = "openai"
os.environ["OPENAI_USE_RESPONSES_API"] = "false"
os.environ["LLM_REDUCE_TOOLS_ENABLED"] = "true"
for variable in (
    "GOOGLE_OAUTH_CLIENT_JSON", "GOOGLE_OAUTH_CLIENT_FILE",
    "GOOGLE_OAUTH_TOKEN_JSON", "GOOGLE_OAUTH_TOKEN_FILE",
    "GOOGLE_SERVICE_ACCOUNT_JSON", "GOOGLE_SERVICE_ACCOUNT_FILE",
):
    os.environ[variable] = ""
