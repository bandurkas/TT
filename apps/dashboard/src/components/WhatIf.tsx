"use client";
import { useLang, useT } from "@/lib/i18n";
import { idr, int, num } from "@/lib/format";
import type { Dec, UnitEconomics } from "@/lib/types";

const PRESETS = [2000, 3000, 4000, 5000];

/** Recompute the period with a different product cost. Only COGS moves: revenue, TikTok fees
 *  and advertising stay at the period's actual figures, so the delta is exactly the COGS delta. */
export function whatIfNet(ue: UnitEconomics | null | undefined, netProfit: Dec | null | undefined, unitCost: number | null) {
  const units = ue?.units ?? 0;
  const nowCogs = num(ue?.cogs_per_unit);
  const now = num(netProfit);
  if (!units || now === null || nowCogs === null || unitCost === null) return null;
  return now + (nowCogs - unitCost) * units;
}

interface Props {
  ue?: UnitEconomics | null; netProfit?: Dec | null;
  pieces: string; setPieces: (v: string) => void;
  perPiece: string; setPerPiece: (v: string) => void;
}

export default function WhatIf({ ue, netProfit, pieces, setPieces, perPiece, setPerPiece }: Props) {
  const lang = useLang(), t = useT();
  const units = ue?.units ?? 0;
  const nowCogsUnit = num(ue?.cogs_per_unit);
  const nowNet = num(netProfit);
  const nPieces = Number(pieces) > 0 ? Number(pieces) : 0;
  const nPerPiece = perPiece === "" ? null : Number(perPiece);
  const whatIfUnit = nPerPiece !== null && nPieces > 0 ? nPerPiece * nPieces : null;
  const canWhatIf = units > 0 && nowNet !== null && nowCogsUnit !== null;
  const ifNet = whatIfNet(ue, netProfit, whatIfUnit);
  const breakEvenUnit = canWhatIf ? nowCogsUnit! + nowNet! / units : null;
  const bePiece = breakEvenUnit !== null && nPieces > 0 ? breakEvenUnit / nPieces : null;
  const delta = ifNet !== null && nowNet !== null ? ifNet - nowNet : null;
  const money = (v: number | null | undefined) => (v === null || v === undefined ? "—" : idr(v, lang));

  if (!canWhatIf) return null;
  return (
    <div className="whatif">
      <div className="row">
        <label className="field">{t("Pieces per unit")}
          <input type="number" min="1" step="1" inputMode="numeric" value={pieces} onChange={(e) => setPieces(e.target.value)} style={{ width: 84 }} /></label>
        <label className="field">{t("Cost per piece")}
          <input type="number" min="0" step="1" inputMode="numeric" placeholder="3000" value={perPiece} onChange={(e) => setPerPiece(e.target.value)} style={{ width: 116 }} /></label>
        <span className="presets" role="group" aria-label={t("Cost per piece")}>
          {PRESETS.map((v) => (
            <button key={v} type="button" onClick={() => setPerPiece(String(v))}
              className={`${bePiece === null ? "" : v < bePiece ? "win" : "lose"} ${Number(perPiece) === v ? "on" : ""}`}>
              {int(v, lang)}
            </button>
          ))}
        </span>
        {whatIfUnit !== null && <span className="eq">= <b>{money(whatIfUnit)}</b> {t("per unit")} × {int(units, lang)}</span>}
      </div>
      {ifNet === null ? <div className="tiny" style={{ marginTop: 10 }}>{t("Enter a price per piece to see the recalculation.")}</div> : (
        <div className="wi-live">
          {t("Product cost for the period")}: <b>{money(whatIfUnit! * units)}</b> <span className="was">({t("Now")}: {money(nowCogsUnit! * units)})</span>
          {delta !== null && delta !== 0 && <> · {t("Net profit")} {delta > 0 ? "+" : "−"}<b>{money(Math.abs(delta))}</b></>}
          <div className="tiny" style={{ marginTop: 4, fontWeight: 400 }}>{t("The cards below are recalculated at this cost. Everything else — revenue, TikTok fees, advertising — stays at the period's actual figures.")}</div>
        </div>
      )}
      <div className="wi-be">
        {t("Break-even product cost")}: {breakEvenUnit !== null && breakEvenUnit < 0
          ? <b>{t("unreachable — the period is unprofitable even at zero product cost")}</b>
          : <><b>{money(breakEvenUnit)}</b> {t("per unit")}{bePiece !== null && <> · <b>{money(bePiece)}</b> {t("per piece")}</>}</>}
        <div className="tiny" style={{ marginTop: 5 }}>{t("Applied uniformly to every SKU, so it is an estimate when SKUs differ in cost. Nothing is saved — set it for real in “Product cost · FIFO” below.")}</div>
      </div>
    </div>
  );
}
