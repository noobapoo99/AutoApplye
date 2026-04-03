| Service | Free Limit | Env Var | Tips to Stay Free |
|---------|-----------|---------|------------------|
| Gemini | 1M tokens/day | GEMINI_API_KEY | LLM cache (built-in) saves 60-80% of calls |
| Groq | 14,400 req/day | GROQ_API_KEY | Only used as fallback — rarely triggered |
| CloudAMQP | 1M msgs/month | RABBITMQ_URL | Each job pipeline = ~5 messages |
| Upstash | 10K cmds/day | REDIS_URL | Cache + rate limiter = ~30 cmds per pipeline |
| Supabase | 500MB DB | DATABASE_URL | Text data only — stays well under limit |
| SerpAPI | 100/month | SERPAPI_KEY | Most constrained — use narrow queries |
| Render.com | 750 hrs/month | — | Workers + API = ~4 services, each counts |
| Vercel | Unlimited | — | No concerns for this use case |
