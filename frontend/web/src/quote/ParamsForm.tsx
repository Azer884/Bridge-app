import { useState } from "react";
import type { ExtractedParams, ParamField, ParamValue } from "@shared/types";
import { showValue } from "@shared/params";

interface Props {
  params: ExtractedParams;
  values: Record<string, ParamValue>;
  errors: Record<string, string>;
  readOnly: boolean;
  onChange: (key: string, value: ParamValue) => void;
  onReset: (key: string) => void;
}

const LOW = 0.7;

/** Fields come from the backend schema, so any trade works. AI values stay visible next to the owner's. */
export function ParamsForm({ params, values, errors, readOnly, onChange, onReset }: Props) {
  const [raw, setRaw] = useState<Record<string, string>>(() =>
    Object.fromEntries(params.schema.filter((f) => f.type === "number").map((f) => [f.key, values[f.key] == null ? "" : String(values[f.key])])),
  );

  const resetRaw = (f: ParamField) => setRaw((r) => ({ ...r, [f.key]: params.ai[f.key] == null ? "" : String(params.ai[f.key]) }));

  return (
    <div className="params">
      {params.schema.map((f) => {
        const v = values[f.key];
        const ai = params.ai[f.key];
        const changed = v !== ai;
        const waiting = ai == null && v == null;
        const conf = params.confidence[f.key];
        const low = conf != null && conf < LOW;
        const err = errors[f.key];
        const id = `p-${f.key}`;
        return (
          <div key={f.key} className={`param${changed && !waiting ? " changed" : ""}${err ? " bad" : ""}`}>
            <label htmlFor={id}>{f.label}</label>
            {readOnly ? (
              <div className="param-ro">{showValue(f, v)}</div>
            ) : f.type === "select" ? (
              <select id={id} className="select" value={v == null ? "" : String(v)} onChange={(e) => onChange(f.key, e.target.value)} aria-invalid={!!err}>
                {v == null && <option value="">Waiting for customer</option>}
                {f.options!.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            ) : (
              <div className="unit-input">
                <input
                  id={id}
                  className="input num"
                  inputMode="decimal"
                  placeholder={waiting ? "Waiting for customer" : ""}
                  value={raw[f.key] ?? ""}
                  aria-invalid={!!err}
                  aria-describedby={err ? `${id}-e` : undefined}
                  onChange={(e) => {
                    const t = e.target.value.replace(/[^0-9.]/g, "");
                    setRaw((r) => ({ ...r, [f.key]: t }));
                    onChange(f.key, t === "" || Number.isNaN(Number(t)) ? null : Number(t));
                  }}
                />
                {f.unit && <span>{f.unit}</span>}
              </div>
            )}
            {err && <small id={`${id}-e`} className="err">{err}</small>}
            {!err && f.help && <small className="muted">{f.help}</small>}
            {!readOnly && low && !changed && <small className="low">Gesir is not sure ({Math.round(conf * 100)}%). Check the photos.</small>}
            {!readOnly && changed && !waiting && (
              <small className="ovr">
                Gesir read: {showValue(f, ai)}.{" "}
                <button type="button" className="link" onClick={() => { onReset(f.key); resetRaw(f); }}>Use Gesir's value</button>
              </small>
            )}
          </div>
        );
      })}
    </div>
  );
}
