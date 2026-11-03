import os

# Must be set before any application import: never load a developer's private config.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["BOT_TOKEN"] = "123456:TEST_ONLY_NOT_A_REAL_TOKEN"
os.environ["API_SECRET_TOKEN"] = "test-secret"
