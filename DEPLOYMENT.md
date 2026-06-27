# Todozee Price Fetcher — AWS Deployment

Production deployment of the India Gold & Silver rate API (`safe_price_fetcher.py`)
on AWS, provisioned with Terraform, monitored with CloudWatch, and deployable via
GitHub Actions CI/CD.

## Architecture

```
            Internet
               │  :443 / :80
               ▼
        ┌──────────────┐   reverse_proxy   ┌────────────────────────┐
        │  Caddy (TLS) │ ────────────────▶ │ waitress :5006 (Flask) │
        │  auto HTTPS  │                    │  safe_price_fetcher.py │
        └──────────────┘                    │  systemd: todozee-price│
               ▲                            └────────────────────────┘
   price.chatbucket.chat                              │ stdout -> /var/log/todozee-price/app.log
   (A-record -> EIP)                                  ▼
                                          CloudWatch agent -> /todozee-price/app
                                                          -> /todozee-price/bootstrap
                                                          -> metric filters -> alarms -> SNS email
```

- **Region:** ap-south-1 (Mumbai)
- **Account:** 637560253183
- **Compute:** single `t3.small` EC2 (AL2023), Elastic IP `13.201.210.97`
- **State:** S3 `todozee-tfstate-637560253183`, key `price-fetcher/main.tfstate` (native S3 lock)
- **Shell access:** AWS SSM Session Manager (no SSH key, no port 22 open)
- **Open ports:** 80 + 443 only (Caddy). App port 5006 is localhost-only.

## Live endpoints (after DNS + cert)

`https://price.chatbucket.chat`

| Endpoint | Description |
|---|---|
| `GET /api/rates` | Latest gold & silver |
| `GET /api/rates/gold` | Gold only |
| `GET /api/rates/silver` | Silver only |
| `GET /api/rates/history` | Last 30 records |
| `GET /api/logs` | Recent in-memory log lines |
| `GET /api/health` | Health check |

## One remaining manual step — DNS

Add this record in **Namecheap** (Advanced DNS for `chatbucket.chat`):

```
Type: A   Host: price   Value: 13.201.210.97   TTL: Automatic
```

Caddy retries ACME automatically, so HTTPS goes live a minute or two after the
record propagates. Until then, verify the app over SSM (`curl localhost:5006/api/health`).

## Monitoring

- **Log groups:** `/todozee-price/app`, `/todozee-price/bootstrap` (30-day retention)
- **Metric filters** (namespace `Todozee/Price`): `FetchAllFailed`, `AppErrors`, `FetchSuccess`
- **Alarms** -> SNS `todozee-price-alerts` -> email `udathak@gmail.com`:
  - `todozee-price-fetch-all-failed` — every price source failed
  - `todozee-price-app-errors` — Python traceback in logs
  - `todozee-price-cpu-high` — CPU > 80% sustained
  - `todozee-price-ec2-status-check` — instance/system status check fail
  - `todozee-price-ec2-auto-recover` — auto-recovers the instance on system failure
- **Dashboard:** `Todozee-Price-Fetcher` (fetch metrics, CPU, network, mem/disk, status checks, live log tail)

> The SNS email subscription must be **confirmed** (click the link AWS emails to
> udathak@gmail.com) before alarms can deliver.

## CI/CD (GitHub Actions) — dormant until secret is set

`.github/workflows/ci-cd.yml` deploys on push to `main` via SSM RunCommand
(OIDC, no static keys). It no-ops safely until enabled.

To enable:
1. Push this repo (incl. `terraform/`, `deploy/`, `.github/`) to GitHub.
2. Add repo secret **`AWS_DEPLOY_ROLE_ARN`** =
   `arn:aws:iam::637560253183:role/todozee-price-github-deploy`
   (Settings → Secrets and variables → Actions).

On each push it runs `sudo /usr/local/bin/deploy-app.sh <sha>` on the instance:
`git fetch/checkout` → `pip install` → `systemctl restart` → `/api/health` gate.

## Operations

```bash
# Open a shell (no SSH key needed)
aws ssm start-session --target <instance-id> --region ap-south-1

# Manual deploy / restart from your machine
aws ssm send-command --region ap-south-1 --instance-ids <instance-id> \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["sudo /usr/local/bin/deploy-app.sh"]'

# On the box
systemctl status todozee-price caddy amazon-cloudwatch-agent
journalctl -u todozee-price -f
tail -f /var/log/todozee-price/app.log
```

## Terraform

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

Editing `user_data.sh.tftpl` replaces the instance on the next apply
(`user_data_replace_on_change = true`); the Elastic IP is retained.
