-- ═══════════════════════════════════════════
--  ROGUE MERCHANT — Database Schema + Seeds
-- ═══════════════════════════════════════════
SET NAMES utf8mb4;


CREATE DATABASE IF NOT EXISTS rogue_merchant
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE rogue_merchant;

-- ─── ITEMS CATALOG ────────────────────────────────────────────────────────────
-- These are the tradeable goods in the fantasy bazaar.
-- base_price is used as the center-point for price generation.

CREATE TABLE IF NOT EXISTS items (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100)  NOT NULL,
    emoji       VARCHAR(10)   NOT NULL,
    base_price  INT           NOT NULL,
    description VARCHAR(200),
    category    ENUM('common','uncommon','rare','exotic') NOT NULL DEFAULT 'common'
);

-- ─── GAME SESSIONS ────────────────────────────────────────────────────────────
-- One row per player game run.

CREATE TABLE IF NOT EXISTS game_sessions (
    id            VARCHAR(36)   PRIMARY KEY,
    player_name   VARCHAR(100)  NOT NULL DEFAULT 'Merchant',
    current_round INT           NOT NULL DEFAULT 1,
    gold          DECIMAL(10,2) NOT NULL DEFAULT 500.00,
    status        ENUM('active','completed') NOT NULL DEFAULT 'active',
    final_score   DECIMAL(10,2) DEFAULT NULL,
    created_at    TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);

-- ─── MARKET PRICES ────────────────────────────────────────────────────────────
-- All 10 rounds of prices are PRE-GENERATED at game start and stored here.
-- This is the core DB-justification: player cannot inspect future prices
-- from the client; all logic lives server-side.

CREATE TABLE IF NOT EXISTS market_prices (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    session_id    VARCHAR(36)   NOT NULL,
    item_id       INT           NOT NULL,
    round_number  INT           NOT NULL,
    price         DECIMAL(10,2) NOT NULL,
    trend         ENUM('rising','falling','stable') NOT NULL DEFAULT 'stable',
    FOREIGN KEY (session_id) REFERENCES game_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id)    REFERENCES items(id),
    UNIQUE KEY uq_session_item_round (session_id, item_id, round_number)
);

-- ─── PLAYER INVENTORY ─────────────────────────────────────────────────────────
-- Tracks what the player currently holds and their weighted-average cost basis.

CREATE TABLE IF NOT EXISTS player_inventory (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    session_id     VARCHAR(36)   NOT NULL,
    item_id        INT           NOT NULL,
    quantity       INT           NOT NULL DEFAULT 0,
    avg_buy_price  DECIMAL(10,4) NOT NULL DEFAULT 0.0000,
    FOREIGN KEY (session_id) REFERENCES game_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id)    REFERENCES items(id),
    UNIQUE KEY uq_session_item (session_id, item_id)
);

-- ─── TRANSACTIONS ─────────────────────────────────────────────────────────────
-- Full audit log: every buy/sell action with P&L calculated at sell time.

CREATE TABLE IF NOT EXISTS transactions (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    session_id   VARCHAR(36)   NOT NULL,
    item_id      INT           NOT NULL,
    round_number INT           NOT NULL,
    action       ENUM('buy','sell') NOT NULL,
    quantity     INT           NOT NULL,
    price        DECIMAL(10,2) NOT NULL,
    total        DECIMAL(10,2) NOT NULL,
    profit_loss  DECIMAL(10,2) DEFAULT NULL,   -- NULL for buys, calculated for sells
    created_at   TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES game_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (item_id)    REFERENCES items(id)
);

-- ─── SEED: ITEMS ──────────────────────────────────────────────────────────────
-- 8 fantasy items across 4 rarity tiers with varied base prices.
-- Higher base_price items = bigger absolute swings; lower = safer.

INSERT INTO items (name, emoji, base_price, description, category) VALUES
('Dragon Scales',   '🐉', 155, 'Impervious scales shed by ancient wyrms',          'rare'),
('Phoenix Feather', '🔥', 210, 'Burns eternally without fuel or flame',             'exotic'),
('Moon Crystal',    '🌙',  75, 'Harvested only during a lunar eclipse',             'common'),
('Shadow Silk',     '🕸️',  55, 'Woven by blind spiders deep underground',           'common'),
('Storm Ore',       '⚡', 125, 'Forged inside thunderclouds by lightning itself',   'uncommon'),
('Ancient Tome',    '📜',  90, 'Forbidden knowledge sealed in crumbling parchment', 'uncommon'),
('Mermaid Pearl',   '🐚', 115, 'Glows with an inner tide-light beneath the moon',   'uncommon'),
('Void Shard',      '💎', 185, 'A fragment torn from the edge of another dimension','rare');
