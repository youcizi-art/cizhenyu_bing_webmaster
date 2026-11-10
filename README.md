# cizhenyu_bing_webmaster

Bing Webmaster Tools MCP for 词真语 Deploy.

## Secrets

Do **not** commit API keys.

Deploy injects:

- `CIZHENYU_AUTH_DIR` → `bing.json` (`apiKey`)
- and/or `BING_WEBMASTER_API_KEY`

## Run

```bash
python server.py
```
