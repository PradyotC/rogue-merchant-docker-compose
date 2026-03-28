"""
Rogue Merchant — Flask Backend
All game logic lives here. Prices are pre-generated server-side;
the client never has access to future rounds.
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import mysql.connector
import uuid
import random
import os

app = Flask(__name__)
CORS(app)

# ─── DB CONFIG ──────────────────────────────────────────────────────────────
DB_CONFIG = {
    'host':     os.environ.get('DB_HOST', 'localhost'),
    'user':     os.environ.get('DB_USER', 'root'),
    'password': os.environ.get('DB_PASSWORD', 'roguemerchant'),
    'database': os.environ.get('DB_NAME', 'rogue_merchant'),
    'charset':  'utf8mb4',
    'collation': 'utf8mb4_unicode_ci',
}

def get_db():
    return mysql.connector.connect(**DB_CONFIG)


# ─── PRICE GENERATION ───────────────────────────────────────────────────────
def generate_prices(base_price: float, rounds: int = 10) -> list[float]:
    """
    Simulate a realistic market using trending random walk.
    - trend:  slow-moving directional bias that drifts each round
    - noise:  high-frequency random component each round
    - result: clamped to [35%, 280%] of base to prevent extreme outliers
    """
    prices = []
    current = float(base_price)
    trend = random.uniform(-0.04, 0.04)        # starting market bias

    for _ in range(rounds):
        trend += random.uniform(-0.025, 0.025)  # trend drift
        trend  = max(-0.09, min(0.09, trend))   # trend clamp

        noise  = random.uniform(-0.13, 0.13)    # round noise
        factor = 1.0 + trend + noise
        current *= factor

        # Hard price floor / ceiling
        current = max(base_price * 0.35, min(base_price * 2.8, current))
        prices.append(round(current, 2))

    return prices


# ─── ROUTES ─────────────────────────────────────────────────────────────────

@app.route('/api/new-game', methods=['POST'])
def new_game():
    """
    Create a new game session.
    Generates all 10 rounds of prices upfront and stores them in market_prices.
    Player starts with 500 gold.
    """
    data        = request.json or {}
    player_name = str(data.get('player_name', 'Merchant'))[:50]
    session_id  = str(uuid.uuid4())

    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            "INSERT INTO game_sessions (id, player_name, gold) VALUES (%s, %s, 500.00)",
            (session_id, player_name)
        )

        cursor.execute("SELECT * FROM items")
        items = cursor.fetchall()

        for item in items:
            prices = generate_prices(item['base_price'])

            for round_num, price in enumerate(prices, start=1):
                if round_num > 1:
                    prev = prices[round_num - 2]
                    if   price > prev * 1.06: trend = 'rising'
                    elif price < prev * 0.94: trend = 'falling'
                    else:                     trend = 'stable'
                else:
                    trend = 'stable'

                cursor.execute(
                    """INSERT INTO market_prices
                           (session_id, item_id, round_number, price, trend)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (session_id, item['id'], round_num, price, trend)
                )

            # Pre-create inventory slot so UPDATE (not INSERT) is always safe
            cursor.execute(
                "INSERT INTO player_inventory (session_id, item_id, quantity) VALUES (%s, %s, 0)",
                (session_id, item['id'])
            )

        db.commit()
        return jsonify({'session_id': session_id, 'player_name': player_name, 'starting_gold': 500})

    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        cursor.close()
        db.close()


@app.route('/api/market/<session_id>', methods=['GET'])
def get_market(session_id):
    """
    Return all items with their current-round price, trend, owned quantity,
    and a directional hint for the NEXT round (kept server-side — the client
    just sees an emoji).
    """
    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT current_round, status FROM game_sessions WHERE id = %s",
            (session_id,)
        )
        session = cursor.fetchone()
        if not session:
            return jsonify({'error': 'Session not found'}), 404

        r = session['current_round']

        cursor.execute("""
            SELECT
                i.id, i.name, i.emoji, i.base_price, i.description, i.category,
                mp.price, mp.trend,
                COALESCE(pi.quantity,      0) AS owned,
                COALESCE(pi.avg_buy_price, 0) AS avg_buy_price
            FROM items i
            JOIN market_prices mp
                 ON i.id = mp.item_id
                AND mp.session_id   = %s
                AND mp.round_number = %s
            LEFT JOIN player_inventory pi
                 ON i.id = pi.item_id
                AND pi.session_id = %s
            ORDER BY i.base_price DESC
        """, (session_id, r, session_id))

        items = cursor.fetchall()

        for item in items:
            item['price']         = float(item['price'])
            item['avg_buy_price'] = float(item['avg_buy_price'])

            # Compute next-round direction hint (never revealed as a raw price)
            if r < 10:
                cursor.execute(
                    """SELECT price FROM market_prices
                       WHERE session_id = %s AND item_id = %s AND round_number = %s""",
                    (session_id, item['id'], r + 1)
                )
                nxt = cursor.fetchone()
                if nxt:
                    diff = (float(nxt['price']) - item['price']) / item['price']
                    if   diff >  0.07: item['hint'] = '📈'
                    elif diff < -0.07: item['hint'] = '📉'
                    else:              item['hint'] = '➡️'
            else:
                item['hint'] = '🏁'   # final round flag

        return jsonify({'round': r, 'items': items, 'status': session['status']})
    finally:
        cursor.close()
        db.close()


@app.route('/api/portfolio/<session_id>', methods=['GET'])
def get_portfolio(session_id):
    """Return gold balance, held items (with unrealized P&L), and total net worth."""
    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT gold, current_round FROM game_sessions WHERE id = %s",
            (session_id,)
        )
        session = cursor.fetchone()
        if not session:
            return jsonify({'error': 'Not found'}), 404

        cursor.execute("""
            SELECT
                i.name, i.emoji,
                pi.quantity,
                pi.avg_buy_price,
                mp.price                                         AS current_price,
                (mp.price - pi.avg_buy_price) * pi.quantity     AS unrealized_pl
            FROM player_inventory pi
            JOIN items i  ON pi.item_id = i.id
            JOIN market_prices mp
                 ON pi.item_id = mp.item_id
                AND mp.session_id   = %s
                AND mp.round_number = %s
            WHERE pi.session_id = %s AND pi.quantity > 0
            ORDER BY unrealized_pl DESC
        """, (session_id, session['current_round'], session_id))

        holdings = cursor.fetchall()
        for h in holdings:
            h['avg_buy_price'] = float(h['avg_buy_price'])
            h['current_price'] = float(h['current_price'])
            h['unrealized_pl'] = float(h['unrealized_pl'])

        portfolio_value = sum(h['quantity'] * h['current_price'] for h in holdings)
        gold            = float(session['gold'])

        return jsonify({
            'gold':            gold,
            'holdings':        holdings,
            'portfolio_value': round(portfolio_value, 2),
            'total_worth':     round(gold + portfolio_value, 2),
        })
    finally:
        cursor.close()
        db.close()


@app.route('/api/buy', methods=['POST'])
def buy_item():
    """
    Purchase `quantity` units of an item.
    Updates gold, inventory (weighted-avg cost basis), and logs the transaction.
    """
    data       = request.json or {}
    session_id = data.get('session_id')
    item_id    = data.get('item_id')
    quantity   = max(1, int(data.get('quantity', 1)))

    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT gold, current_round, status FROM game_sessions WHERE id = %s",
            (session_id,)
        )
        session = cursor.fetchone()
        if not session:
            return jsonify({'error': 'Session not found'}), 404
        if session['status'] == 'completed':
            return jsonify({'error': 'Game is already over'}), 400

        cursor.execute(
            "SELECT price FROM market_prices WHERE session_id=%s AND item_id=%s AND round_number=%s",
            (session_id, item_id, session['current_round'])
        )
        price_row = cursor.fetchone()
        if not price_row:
            return jsonify({'error': 'Item not found in market'}), 404

        price      = float(price_row['price'])
        total_cost = round(price * quantity, 2)
        gold       = float(session['gold'])

        if gold < total_cost:
            return jsonify({'error': f'Need {round(total_cost)}g but only have {round(gold)}g'}), 400

        # Deduct gold
        cursor.execute(
            "UPDATE game_sessions SET gold = gold - %s WHERE id = %s",
            (total_cost, session_id)
        )

        # Weighted-average cost basis update
        cursor.execute(
            "SELECT quantity, avg_buy_price FROM player_inventory WHERE session_id=%s AND item_id=%s",
            (session_id, item_id)
        )
        inv     = cursor.fetchone()
        old_qty = inv['quantity']
        old_avg = float(inv['avg_buy_price'])
        new_qty = old_qty + quantity
        new_avg = ((old_avg * old_qty) + (price * quantity)) / new_qty

        cursor.execute(
            "UPDATE player_inventory SET quantity=%s, avg_buy_price=%s WHERE session_id=%s AND item_id=%s",
            (new_qty, round(new_avg, 4), session_id, item_id)
        )

        # Log
        cursor.execute(
            """INSERT INTO transactions
                   (session_id, item_id, round_number, action, quantity, price, total)
               VALUES (%s, %s, %s, 'buy', %s, %s, %s)""",
            (session_id, item_id, session['current_round'], quantity, round(price, 2), total_cost)
        )

        db.commit()
        return jsonify({'success': True, 'spent': total_cost})

    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        cursor.close()
        db.close()


@app.route('/api/sell', methods=['POST'])
def sell_item():
    """
    Sell `quantity` units.
    Calculates realized P&L against weighted-average cost basis.
    """
    data       = request.json or {}
    session_id = data.get('session_id')
    item_id    = data.get('item_id')
    quantity   = max(1, int(data.get('quantity', 1)))

    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT gold, current_round FROM game_sessions WHERE id = %s",
            (session_id,)
        )
        session = cursor.fetchone()

        cursor.execute(
            "SELECT quantity, avg_buy_price FROM player_inventory WHERE session_id=%s AND item_id=%s",
            (session_id, item_id)
        )
        inv = cursor.fetchone()

        if not inv or inv['quantity'] < quantity:
            owned = inv['quantity'] if inv else 0
            return jsonify({'error': f'Only own {owned}, cannot sell {quantity}'}), 400

        cursor.execute(
            "SELECT price FROM market_prices WHERE session_id=%s AND item_id=%s AND round_number=%s",
            (session_id, item_id, session['current_round'])
        )
        price_row   = cursor.fetchone()
        price       = float(price_row['price'])
        total_earn  = round(price * quantity, 2)
        profit_loss = round((price - float(inv['avg_buy_price'])) * quantity, 2)

        # Credit gold
        cursor.execute(
            "UPDATE game_sessions SET gold = gold + %s WHERE id = %s",
            (total_earn, session_id)
        )

        # Update inventory
        new_qty = inv['quantity'] - quantity
        if new_qty == 0:
            cursor.execute(
                "UPDATE player_inventory SET quantity=0, avg_buy_price=0 WHERE session_id=%s AND item_id=%s",
                (session_id, item_id)
            )
        else:
            cursor.execute(
                "UPDATE player_inventory SET quantity=%s WHERE session_id=%s AND item_id=%s",
                (new_qty, session_id, item_id)
            )

        # Log
        cursor.execute(
            """INSERT INTO transactions
                   (session_id, item_id, round_number, action, quantity, price, total, profit_loss)
               VALUES (%s, %s, %s, 'sell', %s, %s, %s, %s)""",
            (session_id, item_id, session['current_round'],
             quantity, round(price, 2), total_earn, profit_loss)
        )

        db.commit()
        return jsonify({'success': True, 'earned': total_earn, 'profit_loss': profit_loss})

    except Exception as exc:
        db.rollback()
        return jsonify({'error': str(exc)}), 500
    finally:
        cursor.close()
        db.close()


@app.route('/api/next-round', methods=['POST'])
def next_round():
    """
    Advance to the next round.
    On round 10: liquidate remaining inventory at round-10 prices,
    calculate final score, mark session complete.
    """
    data       = request.json or {}
    session_id = data.get('session_id')

    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT current_round, gold, status FROM game_sessions WHERE id = %s",
            (session_id,)
        )
        session = cursor.fetchone()
        if not session:
            return jsonify({'error': 'Not found'}), 404
        if session['status'] == 'completed':
            return jsonify({'game_over': True})

        if session['current_round'] >= 10:
            # Final score = cash + value of remaining items at round-10 prices
            cursor.execute("""
                SELECT COALESCE(SUM(pi.quantity * mp.price), 0) AS portfolio_value
                FROM player_inventory pi
                JOIN market_prices mp
                     ON pi.item_id = mp.item_id
                    AND mp.session_id   = %s
                    AND mp.round_number = 10
                WHERE pi.session_id = %s AND pi.quantity > 0
            """, (session_id, session_id))

            pv              = cursor.fetchone()
            portfolio_value = float(pv['portfolio_value'])
            final_score     = round(float(session['gold']) + portfolio_value, 2)

            cursor.execute(
                "UPDATE game_sessions SET status='completed', final_score=%s WHERE id=%s",
                (final_score, session_id)
            )
            db.commit()
            return jsonify({'game_over': True, 'final_score': final_score})

        cursor.execute(
            "UPDATE game_sessions SET current_round = current_round + 1 WHERE id = %s",
            (session_id,)
        )
        db.commit()
        return jsonify({'round': session['current_round'] + 1, 'game_over': False})

    finally:
        cursor.close()
        db.close()


@app.route('/api/price-history/<session_id>/<int:item_id>', methods=['GET'])
def price_history(session_id, item_id):
    """Return the price history for one item up to the current round (for sparklines)."""
    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT current_round FROM game_sessions WHERE id = %s",
            (session_id,)
        )
        session = cursor.fetchone()
        if not session:
            return jsonify([])

        cursor.execute("""
            SELECT round_number, price, trend
            FROM market_prices
            WHERE session_id = %s AND item_id = %s AND round_number <= %s
            ORDER BY round_number ASC
        """, (session_id, item_id, session['current_round']))

        history = cursor.fetchall()
        for h in history:
            h['price'] = float(h['price'])
        return jsonify(history)
    finally:
        cursor.close()
        db.close()


@app.route('/api/transactions/<session_id>', methods=['GET'])
def get_transactions(session_id):
    """Full trade log for the session (most recent first, capped at 25)."""
    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT
                t.action, t.quantity, t.price, t.total, t.profit_loss,
                t.round_number, t.created_at,
                i.name, i.emoji
            FROM transactions t
            JOIN items i ON t.item_id = i.id
            WHERE t.session_id = %s
            ORDER BY t.created_at DESC
            LIMIT 25
        """, (session_id,))

        txns = cursor.fetchall()
        for t in txns:
            t['price']       = float(t['price'])
            t['total']       = float(t['total'])
            t['profit_loss'] = float(t['profit_loss']) if t['profit_loss'] is not None else None
            t['created_at']  = str(t['created_at'])
        return jsonify(txns)
    finally:
        cursor.close()
        db.close()

@app.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    """Return the top 10 highest-scoring completed games."""
    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT player_name, final_score, created_at
            FROM game_sessions
            WHERE status = 'completed' AND final_score IS NOT NULL
            ORDER BY final_score DESC
            LIMIT 10
        """)
        leaders = cursor.fetchall()
        
        for l in leaders:
            l['final_score'] = float(l['final_score'])
            l['created_at']  = str(l['created_at'])
            
        return jsonify(leaders)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500
    finally:
        cursor.close()
        db.close()

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
