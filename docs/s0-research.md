# S0 Research — Kalshi venue mechanics

*Researched 2026-10-13 (evening CT). All API checks were unauthenticated, read-only GETs against
`https://external-api.kalshi.com/trade-api/v2` (about 60 requests in total, well under the rate limit). No keys were used.*

Facts can change. Each answer gives its source and the date it was checked. "Live API" means I called the endpoint
myself on 2026-10-13. "Docs" means docs.kalshi.com.

---

## ⚠️ Findings that change the plan

1. **A public trade tape exists. It is complete, persistent and can be backfilled.** `GET /markets/trades` needs no
   auth. Each trade has a microsecond `created_time`, a fractional size (`count_fp`), the price, and the **aggressor side**
   (`taker_outcome_side` / `taker_book_side`). Trades stay queryable after the game. → The recorder doesn't need
   to poll trades live. It can fetch each game's trades once, after the window closes, which gives a complete,
   gap-free tape. Live book snapshots are the only thing that must be captured in real time.
2. **Past games can be backfilled.** This includes trades and 1-minute candles with yes-bid/yes-ask OHLC, but not
   depth. Trades older than the cutoff (currently 2026-08-14) move to `/historical/trades`, which is also public; I
   confirmed trades from 2025-12-31 there. → We could run an *exploratory* S2 pilot on NFL weeks 1–6 and last
   season's NBA/NHL now, at 1-minute top-of-book resolution only. **This creates a pre-registration risk**: see
   "Criteria review" below. Ian should decide how historical data is treated *before* anyone looks at it.
3. **`occurrence_datetime` on a market is NOT the game start.** It is the expected *end* (start + ~3 h). The
   scheduled start is the **milestone `start_date`** (`GET /milestones?related_event_ticker=…`). Example: PIT@UTA has
   milestone start `2026-10-20T01:00Z` (7 pm MT) but market `occurrence_datetime` `04:00Z`. The recorder must use milestones.
4. **WebSockets require API keys**, even for public channels. That conflicts with the "no keys at this stage" rule, so
   the recorder polls REST. `GET /markets/orderbooks?tickers=…` returns up to **100 books in one request**, so a whole
   slate fits in one call every 2–3 s. *Open question:* whether that call is billed per ticker. If it is, 40 tickers
   every 2 s ≈ the full Basic read budget. Measure during the Oct 15–16 test run, and fall back to one market per game
   or 3 s polling if needed.
5. **Maker fees are confirmed at 0.25× taker on all three series**, with no pending changes. At 50¢ the maker fee is
   **0.4375¢/contract** (round trip ≈ 0.875¢), versus 1.75¢ for a taker.
6. **No liquidity incentives apply to the game markets.** None are active, upcoming, or anywhere in the closed history
   the API returns (Mar–Oct 2026). Treat incentives as zero. Re-check on recording days, because programs are set per market.
7. **The pre-game spread on a liquid game can be 1¢**, which is the minimum tick. Example: VGK@MIN at scheduled start
   (Oct 13 00:00Z) was yes bid 0.50 / ask 0.51. You can't quote *inside* a 1¢ spread, so queue position decides
   everything and the "assume last in queue" rule will bite. This affects the S2 gate wording (see review).

---

## Answers to the S0 questions

### 1. Maker/taker fees for KXNFLGAME / KXNBAGAME / KXNHLGAME
| Series | `fee_type` | `fee_multiplier` | Taker fee | Maker fee | Pending change |
|---|---|---|---|---|---|
| KXNFLGAME | `quadratic_with_maker_fees` | 1 | 0.07·C·P·(1−P) | 0.0175·C·P·(1−P) | none |
| KXNBAGAME | `quadratic_with_maker_fees` | 1 | 0.07·C·P·(1−P) | 0.0175·C·P·(1−P) | none |
| KXNHLGAME | `quadratic_with_maker_fees` | 1 | 0.07·C·P·(1−P) | 0.0175·C·P·(1−P) | none |

- **Sources:**
  - Live API `GET /series/{ticker}` (all three show the values above).
  - Live API `GET /series/fee_changes`: 0 pending changes across all series. Historical changes: KXNFLGAME was set to
    `quadratic_with_maker_fees` ×1 on 2026-01-01.
  - [kalshi.com/fee-schedule](https://kalshi.com/fee-schedule): "No upcoming fee changes scheduled". The page lists all
    three series as "maker fees", multiplier 1, taker range $0.07–$1.75 per 100 contracts, and the standard maker range
    of $0.02–$0.44 per 100 contracts.
- **Base coefficient 0.07:** the fee-schedule page's 100-contract range ($1.75 max = 0.07 × 100 × 0.25) is consistent
  with it, and the maker ratio of 0.25 matches $0.44 ≈ 0.0175 × 100 × 0.25. The PDF
  ([kalshi-fee-schedule.pdf](https://kalshi.com/docs/kalshi-fee-schedule.pdf)) blocks automated download (HTTP 429), so
  I couldn't quote it directly. *This also resolves the "unconfirmed 0.07" note in alt-arb's `pricing/fees.py`.*
- **Rounding** ([docs: Fee Rounding](https://docs.kalshi.com/getting_started/fee_rounding)): each fill's fee is rounded
  *up* to $0.000001. A retail account's balance then moves in whole cents. Rounding overpayment goes into a fee
  accumulator, which rebates it once a full cent has built up. This applies across all fills of an order, maker or
  taker. → Over many fills the effective fee converges to the exact formula. For a conservative bound, use ceil-to-cent per order.
- Cancelling a resting order is free.

### 2. Tick size, minimum size, post-only
- **Tick:** set per market by `price_ranges`. The game markets I sampled show `price_level_structure: linear_cent` with
  a single band 0.00–1.00, step **$0.01**. The recorder should read `price_ranges` rather than assume this.
  ([docs: Fixed-Point](https://docs.kalshi.com/getting_started/fixed_point_migration); live API `GET /markets`.)
- **Size:** fractional contracts are allowed, minimum granularity **0.01 contracts**, and real books and trades contain
  fractional sizes (e.g. 102.94, 9.47). Store counts as integer hundredths, which fits rule 5.
- **Post-only:** yes. Create Order V2 has `post_only` (bool), `time_in_force` ∈ {`fill_or_kill`, `good_till_canceled`,
  `immediate_or_cancel`}, an optional `expiration_time`, `self_trade_prevention_type`, `reduce_only`, and
  `cancel_order_on_pause`. **Order groups** can auto-cancel all of a group's orders when a rolling 15-second
  contract limit is hit, which is useful later for the "pull quotes" rule.
  ([docs: Create Order V2](https://docs.kalshi.com/api-reference/orders/create-order-v2),
  [Order Groups](https://docs.kalshi.com/getting_started/order_groups).)

### 3. Public trade tape (most important)
- **Endpoint:** `GET /markets/trades?ticker=&min_ts=&max_ts=&limit≤1000&cursor=`. Public (no auth); confirmed live.
  ([docs: Get Trades](https://docs.kalshi.com/api-reference/market/get-trades).)
- **Fields per trade:** `trade_id`, `ticker`, `created_time` (ISO, microseconds), `count_fp` (size),
  `yes_price_dollars`, `no_price_dollars`, `taker_outcome_side` (yes/no), `taker_book_side` (bid/ask), `is_block_trade`,
  and the deprecated `taker_side`.
- **Aggressor side:** yes. `bid ≡ yes` always, so `taker_book_side=bid` means the taker bought yes, i.e. lifted the
  yes ask. ([docs: Order direction](https://docs.kalshi.com/getting_started/order_direction).)
- **Sample** (live, KXNHLGAME-26OCT12VGKMIN-VGK, 30 min before to 10 min after scheduled start): 154 trades,
  7,712.67 contracts, median size 18.95, max 663.51, all non-block, 151 distinct timestamps, 154 unique IDs. Takers
  bought yes in 148 of 154 trades. That one-sidedness is worth a look in S2, but it's one game, so don't read anything into it yet.
- **How far back:** the live endpoint holds trades newer than `GET /historical/cutoff` → `trades_created_ts`
  (2026-08-14 on 2026-10-13). Older trades are at `GET /historical/trades`, also public; I confirmed trades from
  2025-12-31. The cutoff moves forward over time, so don't hard-code it.
  ([docs: Historical Data](https://docs.kalshi.com/getting_started/historical_data).)
- **Limit:** the tape shows trades, not order placements or cancels. Queue position ahead of a hypothetical order
  has to be inferred from book snapshots, so "last in queue" stays the right assumption.

### 4. Order book depth from REST
- `GET /markets/{ticker}/orderbook?depth=` takes `depth` 0 = all levels, 1–100 = that many. Public; confirmed live.
  It returns **bids only**: `yes_dollars` and `no_dollars` as `[price, size]` pairs. The yes ask = 1 − best no bid.
  ([docs: Get Market Orderbook](https://docs.kalshi.com/api-reference/market/get-market-orderbook).)
- `GET /markets/orderbooks?tickers=…` returns up to 100 markets per call. Public; confirmed live.
  ([docs](https://docs.kalshi.com/api-reference/market/get-multiple-market-orderbooks).)
- **Ordering discrepancy:** the docs say levels are "best to worst", but live responses came back in *ascending*
  price (worst-to-best for bids). The recorder must sort and must not trust the order.
- The response has no exchange timestamp, so the recorder must store its own fetch timestamps (send and receive).
- 1-minute **candlesticks** (`GET /series/{s}/markets/{t}/candlesticks?period_interval=1`) include yes_bid/yes_ask
  OHLC, trade price OHLC, volume and open interest. Public. They're useful for a historical top-of-book backfill only.

### 5. Rate limits
([docs: Rate Limits](https://docs.kalshi.com/getting_started/rate_limits); live `GET /account/endpoint_costs`, public.)
- Limits are counted in tokens. **Basic: 200 read tokens/s, 100 write tokens/s.** The default cost is 10 tokens per
  request, and every market-data GET I need is default → **Basic ≈ 20 read req/s (confirmed).** The Basic read bucket
  holds 3 s of budget (bursts up to 600 tokens).
- **For later (orders):** creating an order costs 10 tokens → about 10 orders/s on Basic. Cancelling an event order
  costs 2 tokens → about 50/s. Batches are billed per item, and the whole batch must fit in the bucket. The Basic write
  bucket holds only 1 s. A 429 returns no `Retry-After` header, so back off exponentially.
- Whether `GET /markets/orderbooks` is billed per ticker is **not documented**; see plan finding 4.

### 6. Liquidity incentives
- **Volume Incentive Program:** ends ≥ 2026-10-13
  ([gambling.com](https://www.gambling.com/us/news/kalshi-end-volume-incentive-program-october-13),
  [LSR](https://www.legalsportsreport.com/279648/volume-rewards-program-on-kalshi-set-to-end-nearly-a-year-early/)).
  It no longer appears in Kalshi's Programs & Promotions help collection.
- **Liquidity Incentive Program (LIP):** still running until 2027-01-01. Any market can be chosen, per market and per
  period. Rewards go to resting size near the best price on *both* sides, sampled once a second.
  ([help: LIP](https://help.kalshi.com/en/articles/13823851-liquidity-incentive-program),
  [where to find them](https://help.kalshi.com/en/articles/16076644-liquidity-incentive-programs-where-to-find-them).)
- **Do the game markets qualify right now? No.** Live API `GET /incentive_programs`: 5,682 active, 2,475 upcoming and
  15,239 closed programs (closed history back to 2026-03-12). **Zero** were on KXNFLGAME / KXNBAGAME / KXNHLGAME
  markets. The sports programs found are on season-long, prop and novelty series.
- **Sports Prop Combo legs program:** covers player props only; game winners are excluded
  ([help](https://help.kalshi.com/en/articles/17184676-sports-prop-combo-market-component-legs-liquidity-incentive-program)).
- **Liquidity Provider Program:** only for members with a Market Maker Agreement
  ([help](https://help.kalshi.com/en/articles/15410219-liquidity-provider-program)). Not relevant.
- → **Model incentives as zero.** If an LIP shows up on a recorded game, log it, but keep it out of P&L.

### 7. Scheduled start time
- Use **`GET /milestones?related_event_ticker={event}`** → `start_date`. The milestone also has `type`
  (e.g. `hockey_match`), `title`, `details.status`, and team IDs. Confirmed live: VGK@MIN start `2026-10-13T00:00Z`,
  PIT@UTA `2026-10-20T01:00Z`.
  ([docs: Targets & Milestones](https://docs.kalshi.com/getting_started/targets_and_milestones).)
- **Don't** use market `occurrence_datetime` / `expected_expiration_time` (the expected end) or `close_time`.
- Scheduled start ≠ actual kickoff/puck drop. TV start times usually lead the actual start by about 5–15 minutes.
  The S2 jump analysis should mark the actual start time, which can be found as the first big move or from a box score.
- Events for all three series are listed now (`GET /events?series_ticker=…&status=open`). Note that KXNBAGAME has
  **preseason** games (Oct 13), which must be excluded by date (≥ Oct 20).

---

## Review of the DRAFT pre-registered criteria (suggestions only — not applied)

1. **Decide what historical data is for, before anyone looks at it.** Backfill is possible (finding 2). Suggested
   options: (a) historical data is off-limits until S2 on recorded data is done, and is then used as an out-of-sample
   check; or (b) it's an explicitly *exploratory* pilot that doesn't count, and the criteria are frozen first. Record
   the choice in `decisions.md`. (a) is the cleanest.
2. **S2 gate, spread prong.** "Median pre-kickoff spread ≥ 2¢" on its own doesn't make noise tradable, and liquid games
   sit at the 1¢ minimum tick. Suggest dropping the OR, or making it AND, so the gate rests on genuine reversals. Also
   fix the definitions now:
   - *genuine mid move*: the mid changes and stays changed for ≥ N seconds (e.g. 10 s), or both bid and ask move.
   - *reversal*: a move of ≥ X followed by a return of ≥ X within T minutes (e.g. 5).
   - The fee in "spread + 2 × maker fee" should be evaluated at the actual price (0.0175·P·(1−P)), not at 50¢.
3. **S3 fill rule.** "Fills only when the tape shows trades through its price" is good as the primary rule.
   Pre-register one less conservative *sensitivity* run as well: a fill at your price once traded volume at that price
   exceeds the queue ahead (from the last snapshot) plus your size. Report both, but GO/STOP is decided on the
   conservative rule only.
4. **Adverse-selection horizon.** Pre-register the mark-out horizon, e.g. mid 60 s after each fill, plus 10 s and 5 min
   as secondary.
5. **Minimum activity for GO.** "Positive in ≥ 60% of games" can be driven by games with 1–2 fills. Suggest also
   requiring ≥ M total simulated round trips (e.g. ≥ 100), and that a game with 0 fills counts as *not positive*.
   Optionally, require a bootstrap 90% CI on total net P&L that excludes zero.
6. **Fees in P&L.** Use the exact per-fill fee, with ceil-to-cent per order as the conservative variant. Pre-register
   which one decides GO/STOP; the suggestion is the conservative one.
7. **"Clean game" definition.** Since trades can be backfilled, the "no gap > 30 s" rule only needs to apply to book
   snapshots. Also exclude games with a postponement, a trading pause, or an LIP active on the market.
8. **Window.** The window is 30 min before to 10 min after the *scheduled* start, but the actual start can be ~10 min
   late. Suggest +20 min after the scheduled start so every window covers the real kickoff and the first few minutes of play.
9. **Markets per game.** Each game has two complementary markets (one per team). Pre-register whether the simulation
   quotes one (e.g. home team) or both. Quoting both double-counts the same information.

---

## Facts for the recorder (S1)
- REST only, no auth. Every 2–3 s, one `GET /markets/orderbooks?tickers=…` per batch of up to 100 tickers. Store send
  and receive timestamps. Sort the levels yourself.
- Trades: one paginated `GET /markets/trades?ticker&min_ts&max_ts` per market after the window closes, deduplicated by `trade_id`.
- Schedule: from `GET /milestones` → `start_date`. Map milestone → event via `related_event_tickers`.
- Per market: snapshot `fee_type`/`fee_multiplier` (series), `price_ranges`, and any active `incentive_programs` at record time.
- Store prices as integer hundredths of a cent (4-decimal dollars → ×10,000), or as Decimal. Store counts as integer hundredths.
- Reuse candidates (don't copy yet): `~/code/alt/project-osprey/src/altarb/venues/kalshi.py` (was `~/code/alt-arb` until 2026-10-14), `http.py`, `models.py`,
  `pricing/fees.py` (alt-arb HEAD 594878f).
