# 🛸 Rogue Merchant — Fantasy Market Flip (Dockerized Edition)

A single-player trading game built on **Nginx + Flask + MySQL**, fully containerized using Docker.  
Buy and sell fantasy goods across 10 market rounds. Prices fluctuate server-side — the client never sees future rounds until you advance.

---

## 📂 Project Structure

```text
rogue-merchant/
├── compose.yaml              # Orchestrates the 3-tier architecture
├── backend/
│   ├── Dockerfile            # Multi-stage Python build
│   ├── app.py                # Flask API (reads from Env Vars)
│   ├── db.sql                # Schema + 8 seeded items (UTF-8 forced)
│   └── requirements.txt
└── frontend/
    ├── Dockerfile            # Nginx setup
    ├── index.html            # Single-file SPA (no build step)
    └── nginx.conf            # Serves static + proxies /api/ → Flask
```

---

## 🚀 Quick Start (Docker)

Gone are the days of manual MySQL installations, Python virtual environments, and configuring host-level Nginx.

### Prerequisites
* Docker and Docker Compose installed on your machine.

### 1. Launch the Bazaar
Open your terminal in the root `rogue-merchant` directory and run:

```bash
docker compose up -d --build
```
*Docker will build the lightweight Nginx and multi-stage Python images, pull MySQL, set up the network, and inject the `db.sql` schema automatically.*

### 2. Play the Game
Open your browser and navigate to:
**`http://localhost:8080`**

### 3. Resetting / Cleanup
Because this project uses Docker Volumes, your game data and database schema will persist even if you stop the containers. To completely wipe the database and start fresh (destroying the volume):

```bash
docker compose down -v
```

---

## 🐳 Docker Architecture highlights

This project demonstrates several core Docker concepts:

* **Multi-Stage Builds (`backend/Dockerfile`):** The Python API uses a two-stage build. Stage 1 installs heavy build tools and compiles dependencies into a virtual environment. Stage 2 copies *only* that clean environment into a fresh image, resulting in a much smaller, more secure container.
* **Internal Networks (`compose.yaml`):** The three containers communicate over an isolated Docker bridge network (`rogue-net`). The Nginx reverse proxy routes traffic to `http://backend:5000` using Docker's internal DNS—meaning the Flask API doesn't need its port exposed to the host machine at all.
* **Persistent Volumes (`compose.yaml`):** The MySQL database state is mapped to a Docker Volume (`db_data`). If the database container crashes or is recreated, the fantasy market data and player P&L are completely safe.

---

## 🔌 API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/new-game` | Start session, seed 10 rounds of prices |
| GET  | `/api/market/<sid>` | Current round prices + next-round hints |
| GET  | `/api/portfolio/<sid>` | Gold + holdings + net worth |
| POST | `/api/buy` | Buy N items, deduct gold |
| POST | `/api/sell` | Sell N items, calculate P&L |
| POST | `/api/next-round` | Advance round or end game |
| GET  | `/api/price-history/<sid>/<item_id>` | History for sparklines |
| GET  | `/api/transactions/<sid>` | Trade log |
| GET  | `/api/health` | Health check |

---

## 🗄️ Why the Database?

| Feature | DB table used |
|---------|--------------|
| Pre-seeded 10-round prices (hidden from client) | `market_prices` |
| Weighted-average cost basis per item | `player_inventory` |
| Realized P&L on every sell | `transactions` |
| Net worth = gold + portfolio value | `game_sessions` + join |
| Sparkline history | `market_prices` filtered by round ≤ current |

The frontend is completely stateless — the session ID is the only thing stored client-side.

---

## 🏆 Scoring

| Score | Rank |
|-------|------|
| ≥ 1200 gold | 👑 Legendary Merchant |
| ≥  900 gold | ⭐ Great Merchant |
| ≥  600 gold | 🔵 Decent Merchant |
| < 600 gold  | 💀 Ruined Merchant |