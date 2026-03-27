import os

# Setear token dummy para que Settings no falle al importar en tests
os.environ.setdefault("BOT_TOKEN", "test:fake_token_for_testing")
