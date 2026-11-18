# NBA Slate Parlay Builder

A mobile-friendly web app that loads today's NBA slate, pulls live player-prop odds from every major US sportsbook, prices each leg against the market consensus, and ranks parlay combinations by expected value.

**Live app:** https://gcastor.github.io/nba-parlay/

## What it does

- **Loads the day's slate:** lists today's games with Eastern tip times (free API call).
- **Pulls player props on demand:** points, threes, assists and rebounds for the games you choose, from all US books in one request per game.
- **Prices every leg:** removes the vig from each book's over/under, averages the books into a consensus fair probability, and compares it with your sportsbook's price.
- **Suggests parlays:** searches every allowed combination of the best legs and ranks them by expected value, hit probability or payout.
- **Gives you manual control:** number of legs, prop types, overs/unders, minimum edge, minimum hit %, minimum books, max legs per game, and lock/exclude on individual legs.
- **Shows player history:** tap any leg to see the player's last 5 and last 10 games against tonight's line, with hit rate, average, a bar chart and a game log.
- **Shows payouts:** set a wager once, and every suggested parlay shows what it pays.
- **Builds the slip:** combined odds, fair odds, hit %, book's implied %, EV, payout for your stake, and a Kelly stake suggestion.
- **Shops lines:** shows when another book pays more on the same leg.
- **Saves credits:** caches pulled odds in the browser for the day, so reloading is free, and lets you refresh only the games you're about to bet.

## Methodology

**1. No-vig fair probability**

For each player / prop / line, each book's American odds are converted to implied probabilities and normalized so the two sides sum to 1:

```
p_over(book) = imp(over) / (imp(over) + imp(under))
```

The consensus fair probability is the mean of `p_over` across every book quoting both sides of that exact line. A leg needs a minimum number of books (default 3) to be used.

**2. Edge and EV per leg**

```
edge = fair_prob - implied_prob(your book's price)
EV   = fair_prob * decimal_odds - 1
```

Your book's main line for each player/prop is the point whose over/under is closest to a coin flip.

**3. Parlay pricing**

Legs are treated as independent:

```
P(parlay) = Π fair_prob_i
odds      = Π decimal_odds_i
EV        = P(parlay) * odds - 1
```

Legs from the same game are correlated, so suggestions allow one leg per game by default (configurable) and the slip warns when same-game legs are combined.

**4. Combination search**

A recursive search enumerates every combination of the top-N eligible legs (by single-leg EV) that satisfies the constraints: one leg per player, max legs per game, and locked legs always included. Results are sorted by the chosen metric.

**5. Stake sizing**

Fractional Kelly on the parlay:

```
f* = (p * b - (1 - p)) / b      b = decimal_odds - 1
stake = f* × fraction × bankroll   (floored at 0)
```

A stake of $0 means the parlay has no edge at that price.

## Tech stack

| Layer | Choice |
|---|---|
| Front end | One HTML file: vanilla JavaScript and CSS, no framework or build step |
| Data | [The Odds API v4](https://the-odds-api.com/): `/sports/basketball_nba/events` and `/events/{id}/odds` (`regions=us`, player prop markets) |
| Hosting | GitHub Pages |
| Player stats | GitHub Action (`.github/workflows/update-stats.yml`) runs nightly at 4:30 AM ET: `scripts/update_stats.py` pulls finished box scores from ESPN's public site API into `data/player_logs.json` (last 25 games per player), and the app reads that file directly |
| State | Browser `localStorage`: API key, settings, and the day's pulled odds |
| Layout | Responsive CSS grid; stacks to one column on phones; light and dark themes |

There is no server. The only scheduled job is the nightly stats update, which runs on GitHub Actions and commits a static JSON file. The API key is entered by the user, stays in their browser, and is sent only to The Odds API.

## Usage

1. Get a free key at [the-odds-api.com](https://the-odds-api.com/) (500 credits/month).
2. Open the app and paste the key once.
3. Tick the games you want, untick prop types you don't bet, and tap **Pull props**. The button shows the credit cost first.
4. Set the number of legs and filters, then pick a suggestion or add legs to your slip.

**Credit cost:** 1 credit per prop type per game (one region). A 7-game slate with all four prop types costs about 28 credits. Loading the game list is free.

## Limitations

- **Independence assumption:** parlay probabilities multiply legs. Correlated legs (same game, same player) are restricted but not modeled.
- **Consensus is not truth:** fair prices come from the books' own odds. An edge here means your book is out of line with the market, not that the market is wrong.
- **One book at a time:** the parlay is priced at the selected sportsbook. Books also price parlays themselves, so you can enter the book's quoted parlay odds in the slip.
- **No team mapping for players:** The Odds API identifies the game but not the player's team, so per-player home/away isn't shown.

## Related

Part of a season-long NBA player-prop project (`nba-prop-edge`): a Python/SQLite pipeline with a baseline projection model, pre-registered hypotheses, and closing-line-value tracking.

---

For research and entertainment. Not betting advice. Bet only what you can afford to lose.
