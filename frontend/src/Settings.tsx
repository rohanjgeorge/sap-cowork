import { useEffect, useState } from "react";
import { Check, KeyRound, X } from "lucide-react";
import { post, request } from "./api";
import { useModalFocus } from "./useModalFocus";
type Profile = {
  context_window: number;
  max_output_tokens: number;
  structured_output: boolean;
  tool_calling: boolean;
  vision: boolean;
  streaming: boolean;
  reasoning: boolean;
  coding: boolean;
};
type Config = {
  provider: string;
  default_model: string;
  base_url: string | null;
  credential_reference: string | null;
  connection_status: string;
  capabilities: Profile;
};
type SettingsData = {
  default_provider: string;
  providers: Record<string, Config>;
};
const defaultProfile: Profile = {
  context_window: 32000,
  max_output_tokens: 4096,
  structured_output: true,
  tool_calling: false,
  vision: false,
  streaming: false,
  reasoning: true,
  coding: true,
};
export default function Settings({ onClose }: { onClose: () => void }) {
  const dialog = useModalFocus(onClose);
  const [settings, setSettings] = useState<SettingsData | null>(null),
    [provider, setProvider] = useState("fake"),
    [model, setModel] = useState("deterministic-v1"),
    [base, setBase] = useState(""),
    [credential, setCredential] = useState(""),
    [profile, setProfile] = useState(defaultProfile),
    [message, setMessage] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  function select(p: string, data = settings) {
    setProvider(p);
    const c = data?.providers[p];
    setModel(c?.default_model || (p === "fake" ? "deterministic-v1" : ""));
    setBase(c?.base_url || "");
    setCredential("");
    setProfile(c?.capabilities || defaultProfile);
    setMessage("");
  }
  useEffect(() => {
    request<SettingsData>("/settings")
      .then((s) => {
        setSettings(s);
        select(s.default_provider, s);
      })
      .catch((e) => setError(e.message));
  }, []);
  return (
    <div className="modal-backdrop">
      <section
        ref={dialog}
        className="modal settings-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
      >
        <div className="section-heading">
          <div>
            <p className="eyebrow">YOUR MODEL ACCESS</p>
            <h2 id="settings-title">Provider settings</h2>
          </div>
          <button onClick={onClose} aria-label="Close provider settings">
            <X size={17} />
          </button>
        </div>
        <p className="muted">
          <KeyRound size={13} /> Credentials belong to your user settings and
          use the OS credential store. They are excluded from project data.
        </p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              const s = await request<SettingsData>("/settings/provider", {
                method: "PUT",
                body: JSON.stringify({
                  provider,
                  default_model: model,
                  base_url: base || null,
                  credential: credential || null,
                  capabilities: profile,
                }),
              });
              setSettings(s);
              setCredential("");
              setMessage(
                "Provider saved. Test the connection to verify access.",
              );
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Provider
            <select value={provider} onChange={(e) => select(e.target.value)}>
              {["fake", "openai", "anthropic", "qwen", "openai-compatible"].map(
                (p) => (
                  <option key={p}>{p}</option>
                ),
              )}
            </select>
          </label>
          {provider === "fake" && (
            <p className="demo-notice">
              Demo mode produces deterministic sample documents and uses no API
              key. It does not perform substantive SAP design.
            </p>
          )}
          <label>
            Model identifier
            <input
              required
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="Your provider’s model identifier"
            />
          </label>
          {provider !== "fake" && (
            <>
              <label>
                API key
                <input
                  type="password"
                  autoComplete="off"
                  value={credential}
                  onChange={(e) => setCredential(e.target.value)}
                  placeholder={
                    settings?.providers[provider]?.credential_reference
                      ? "Saved credential — leave blank to retain"
                      : "Enter provider API key"
                  }
                />
              </label>
              <label>
                Base URL
                <input
                  type="url"
                  value={base}
                  required={
                    provider === "qwen" || provider === "openai-compatible"
                  }
                  onChange={(e) => setBase(e.target.value)}
                  placeholder="https://your-provider.example/v1"
                />
              </label>
            </>
          )}
          <details>
            <summary>Model capabilities and budget</summary>
            <p className="muted">
              Declare capabilities supported by the chosen model. The gateway
              checks these before execution; provider support is verified at
              request time.
            </p>
            <div className="settings-budget">
              <label>
                Context window
                <input
                  type="number"
                  min="1024"
                  value={profile.context_window}
                  onChange={(e) =>
                    setProfile({
                      ...profile,
                      context_window: Number(e.target.value),
                    })
                  }
                />
              </label>
              <label>
                Output limit
                <input
                  type="number"
                  min="16"
                  value={profile.max_output_tokens}
                  onChange={(e) =>
                    setProfile({
                      ...profile,
                      max_output_tokens: Number(e.target.value),
                    })
                  }
                />
              </label>
            </div>
            <div className="capability-options">
              {(
                [
                  "structured_output",
                  "tool_calling",
                  "vision",
                  "streaming",
                  "reasoning",
                  "coding",
                ] as const
              ).map((c) => (
                <label className="checkbox" key={c}>
                  <input
                    type="checkbox"
                    checked={profile[c]}
                    onChange={(e) =>
                      setProfile({ ...profile, [c]: e.target.checked })
                    }
                  />
                  {c.replaceAll("_", " ")}
                </label>
              ))}
            </div>
          </details>
          {error && <p role="alert">{error}</p>}
          {message && (
            <p role="status" className="saved-message">
              <Check size={14} />
              {message}
            </p>
          )}
          <div className="settings-actions">
            <button className="primary" disabled={busy || !model}>
              {busy ? "Saving…" : "Save provider"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setError("");
                try {
                  const r = await post<{ status: string; provider: string }>(
                    "/settings/provider/test",
                  );
                  setMessage(r.provider + ": " + r.status);
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              Test saved connection
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
