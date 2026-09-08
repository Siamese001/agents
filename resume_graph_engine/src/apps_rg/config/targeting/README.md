# apps_rg targeting inputs

## Briefing

| File pattern | Use |
|--------------|-----|
| `*_briefing.md` | Reference material for target tailoring. It is not a public CLI input. |

### Brown & Brown SVP IT Strategy & Innovation

- Briefing: [brown_brown_svp_it_strategy_innovation_briefing.md](brown_brown_svp_it_strategy_innovation_briefing.md)
- JD: [brown_brown_svp_it_strategy_innovation_jd.txt](brown_brown_svp_it_strategy_innovation_jd.txt)

```powershell
python -m apps_rg run --target-company "Brown & Brown" `
  --target-role "SVP IT Strategy & Innovation" `
  --jd apps_rg/config/targeting/brown_brown_svp_it_strategy_innovation_jd.txt
```

### AIG VP Global Head Agentic AI

- Briefing: [aig_vp_global_head_agentic_ai_briefing.md](aig_vp_global_head_agentic_ai_briefing.md)
- JD: [aig_vp_global_head_agentic_ai_jd.txt](aig_vp_global_head_agentic_ai_jd.txt)

### Citi Head of AI Strategy — Firmwide AI

- JD: [citi_head_of_ai_strategy_jd.txt](citi_head_of_ai_strategy_jd.txt)

```powershell
python -m apps_rg run --target-company "Citi" `
  --target-role "Head of AI Strategy - Firmwide AI" `
  --jd apps_rg/config/targeting/citi_head_of_ai_strategy_jd.txt
```
