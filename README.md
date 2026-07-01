---
title: LinkedIn Post Generator
sdk: docker
app_port: 7860
---

uv run streamlit run streamlit_ui/app.py


uv run streamlit run streamlit_ui/app.py --server.port 7860

Stop-Process -Id 14356

## LinkedIn Burner Session Bootstrap

The app does not automate LinkedIn login. For burner mode, create the isolated
Playwright session once:

```bash
uv run python scripts/bootstrap_linkedin_session.py
```

Log in manually in the opened browser window with a burner account only. After
that, set `LINKEDIN_AUTOMATION_MODE=burner` and the app will reuse the isolated
session in `schema/local_db/playwright/linkedin_burner_profile`.
