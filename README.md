# FlowTrader GEX — Pine Seeds Data Provider

This repo feeds live GEX levels into TradingView via the Pine Seeds program.

## Symbols available

| Symbol | Description |
|---|---|
| `FLOWTRADER:SPY_CALL_WALL` | Top call GEX wall above spot |
| `FLOWTRADER:SPY_PUT_WALL` | Top put GEX wall below spot |
| `FLOWTRADER:SPY_GAMMA_FLIP` | Gamma flip / dealer neutral level |
| `FLOWTRADER:SPY_NET_GEX` | Net GEX (positive = dealers long gamma) |
| `FLOWTRADER:SPY_CALL_GEX_1` | 2nd call wall |
| `FLOWTRADER:SPY_PUT_GEX_1` | 2nd put wall |
| `FLOWTRADER:SPX_CALL_WALL` | SPX call wall |
| `FLOWTRADER:SPX_PUT_WALL` | SPX put wall |
| `FLOWTRADER:SPX_GAMMA_FLIP` | SPX gamma flip |
| `FLOWTRADER:SPX_NET_GEX` | SPX net GEX |

## Update schedule
GitHub Actions runs every 15 minutes during market hours (9:30–16:15 ET, Mon–Fri).

## Pine Seeds registration
Submit this repo at: https://github.com/tradingview/pine-seeds
