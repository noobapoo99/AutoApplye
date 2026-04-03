# Deploying AutoApply (Free)

## 1. Free Accounts You Need

| Service | Purpose | Free Tier | Signup |
|---------|---------|-----------|--------|
| Google AI Studio | Gemini LLM + embeddings | 1M tokens/day | aistudio.google.com |
| Groq | LLaMA3 fallback | 14,400 req/day | console.groq.com |
| CloudAMQP | RabbitMQ broker | 1M msgs/month | cloudamqp.com |
| Upstash | Redis cache | 10K cmds/day | upstash.com |
| Supabase | PostgreSQL | 500MB | supabase.com |
| SerpAPI | Job search | 100/month | serpapi.com |
| Render.com | Backend hosting | 750 hrs/month | render.com |
| Vercel | Frontend hosting | Unlimited | vercel.com |

## 2. Get Your API Keys (step-by-step for each)

For each service above: which dashboard section to click, what to copy,
and which .env key it maps to.

## 3. Database Setup (Supabase)
  Create project → Settings → Database → URI → set DATABASE_URL
  Run: cd backend && alembic upgrade head

## 4. RabbitMQ Setup (CloudAMQP)
  Create instance → Little Lemur plan → copy AMQP URL → set RABBITMQ_URL

## 5. Redis Setup (Upstash)
  Create database → Details → Redis URL (rediss://...) → set REDIS_URL

## 6. Deploy Backend to Render.com
  a. Push project to GitHub
  b. Render dashboard → New → Blueprint → select repo (picks up render.yaml)
  c. Set all env vars in Render dashboard for each service
     List all 15 keys from backend/.env.example
  d. Wait ~5 min for first build
  e. Note: free tier sleeps after 15 min inactivity. First request after sleep
     takes ~20s to wake. Use UptimeRobot (free) to ping /health every 14min.

## 7. Deploy Frontend to Vercel
  a. vercel.com → New Project → Import from GitHub
  b. Root Directory: frontend
  c. Framework: Next.js (auto-detected)
  d. Set env vars:
       NEXT_PUBLIC_API_URL = https://autoapply-api.onrender.com
       NEXT_PUBLIC_WS_URL  = wss://autoapply-api.onrender.com

## 8. Gmail OAuth Setup
  a. console.cloud.google.com → New Project → APIs & Services → Credentials
  b. Create OAuth 2.0 Client ID → Web Application
  c. Authorized redirect URI: https://autoapply-api.onrender.com/auth/gmail/callback
  d. Download credentials → copy Client ID and Secret → add to Render env vars

## 9. Upload Your Resume
  Option A (Render Shell):
    Render dashboard → autoapply-api → Shell
    mkdir -p /app/data
    Upload base_resume.docx via shell

  Option B (API endpoint):
    Add POST /api/resume/upload endpoint to main.py that accepts multipart
    and saves to /app/data/base_resume.docx

## 10. Verify the Deployment
  curl https://autoapply-api.onrender.com/health
  curl -X POST https://autoapply-api.onrender.com/api/jobs/search \
    -H "Content-Type: application/json" \
    -d '{"query":"Python backend engineer","max_jobs":2}'

## 11. Cost & Limits Reference
  Table with columns: Service | Free Limit | Hard Constraint | Upgrade Option
  Include SerpAPI 100/month note (most constrained — use cache heavily)
